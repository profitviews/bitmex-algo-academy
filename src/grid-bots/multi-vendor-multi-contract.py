# 2023-10-03 14:31:00
# Note: this file is to be used within profitview.net/trading/bots
# pylint: disable=locally-disabled, import-self, import-error, missing-class-docstring, invalid-name, consider-using-dict-items, broad-except

import asyncio
import json
import threading
import time

from profitview import Link, http, logger

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d #, CubicSpline
from talib import RSI, MACD

TIME_LOOKUP = {
  '1m':  60_000,
  '5m' : 60_000 * 5,
  '1h':  60_000 * 60,
  '1d':  60_000 * 60 * 24,
}

# GARCH parameters
OMEGA = 1.605025e-08
ALPHA = 0.193613
BETA = 0.786155

def debounce(wait):
  """Postpone a function execution until after wait seconds
  have elapsed since the last time it was invoked.
  source: https://gist.github.com/walkermatt/2871026"""
  def decorator(func):
    def debounced(*args, **kwargs):
      def call_func():
        debounced.last_call = time.time()
        func(*args, **kwargs)

      if hasattr(debounced, 'timer'):
        debounced.timer.cancel()

      if time.time() - getattr(debounced, 'last_call', 0) > wait:
        call_func()
      else:
        debounced.timer = threading.Timer(wait, call_func)
        debounced.timer.start()

    return debounced
  return decorator

# MODES: TAKER_LONG | REDUCE_SHORT | REDUCE_LONG | TAKER_SHORT | GRID | TOB

class Trading(Link):
  ACTIVE = True
  UPDATE_SECONDS = 60
  SHUT_IT_DOWN = False
  GRACEFUL_SHUTDOWN = True
  GRID_BIDS = (40, 30, 20) # (40, 30, 20, 10)
  GRID_ASKS = (60, 70, 80) # (60, 70, 80, 90)
  LOOKBACK = 150
  MACD_RANGE = 4
  CUBIC_N = 40
  LEVEL = '1m'
  ORDER_MULTIPLIER = 5
  REDUCE_TAKER = False
  SRC = 'bitmex'                         # exchange name as in the Glossary
  MAIN_VENUE='account1'
  VENUES = {
      'account1': {
        'XBTUSDT' : {
          'order_size': 1_000 * 400,
          'max_risk': 1_000 * 400 * 10,                  # Means max 10 times the base order size
          'price_precision': 0.5,
          'price_spread': 0.5,
          'size_precision': 1_000,
          'direction': 'FLAT',
          'multiplier': 1,
          'mode' : 'GRID',
          'tob_is_bid' : False,
        },
        'XBTUSD' : {
          'order_size': 100 * 5,
          'max_risk': 100 * 5 * 160,
          'price_precision': 0.5,
          'price_spread': 0.5 * 5,
          'size_precision': 100,
          'direction': 'FLAT',
          'multiplier': 1,
          'mode' : 'GRID',
          'tob_is_bid' : True,
        },
        'ETHUSD' : {
          'order_size': 5,
          'max_risk': 5*100,
          'price_precision': 0.05,
          'size_precision': 1,
          'direction': 'FLAT',
          'multiplier': 1,
        },
        'LINKUSD' : {
          'order_size': 200,
          'max_risk': 200*20,
          'price_precision': 0.001,
          'size_precision': 1,
          'direction': 'FLAT',
          'multiplier': 1,
        },
        'XRPUSD': {
          'order_size': 100,
          'max_risk': 100*20,
          'price_precision': 0.0001,
          'size_precision': 1,
          'direction': 'FLAT',
          'multiplier': 1,
        },
        'SOLUSDT' : {
          'order_size': 1_000 * 500,
          'max_risk': 1_000 * 500 * 20,
          'price_precision': 0.01,
          'size_precision': 1_000,
          'direction': 'FLAT',
          'multiplier': 1,
        },
        'ETHUSDT' : {
          'order_size': 1_000 * 200,
          'max_risk': 1_000 * 200 * 10,
          'price_precision': 0.05,
          'size_precision': 1_000,
          'direction': 'FLAT',
          'multiplier': 1,
        }
      },
      'account2': {
        'XBTUSD' : {
          'order_size': 100 * 4,
          'max_risk': 100 * 4 * 750,
          'price_precision': 0.5,
          'size_precision': 100,
          'direction': 'LONG',
          'multiplier': 1,
        },
      },
    }
  INIT_COMPLETE = False

  def __init__(self):
    super().__init__()
    self.on_start()

  def on_start(self):
    self.time_step = TIME_LOOKUP[self.LEVEL]
    for venue in self.VENUES:
      for sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['sym'] = sym
        self.VENUES[venue][sym]['candles'] = {}
        self.VENUES[venue][sym]['tob'] = (np.nan, np.nan)
        self.VENUES[venue][sym]['mid'] = np.nan
        self.VENUES[venue][sym]['var_t1'] = np.nan
        self.VENUES[venue][sym]['current_risk'] = 0
        self.VENUES[venue][sym]['orders'] = {'bid':{}, 'ask':{}}
        self.VENUES[venue][sym]['macd'] = np.nan
        self.VENUES[venue][sym]['price_decimals'] = str(self.VENUES[venue][sym]['price_precision'])[::-1].find('.')
        self.VENUES[venue][sym]['size_precision'] = self.VENUES[venue][sym].get('size_precision', 1_000)
        self.VENUES[venue][sym]['price_spread'] = self.VENUES[venue][sym].get('price_spread', 0.5)
        self.VENUES[venue][sym]['mode'] = self.VENUES[venue][sym].get('mode', 'GRID')
        self.VENUES[venue][sym]['tob_is_bid'] = self.VENUES[venue][sym].get('tob_is_bid', True)

        candles = self.fetch_candles(self.MAIN_VENUE, sym, level=self.LEVEL)
        self.VENUES[venue][sym]['candles'] = {x['time']: x['close'] for x in candles['data']} | self.VENUES[venue][sym]['candles']

    self.INIT_COMPLETE = True
    asyncio.run(self.minutely_update())

  def hypo_rsi(self, closes, ret):
    return RSI(np.append(closes, [closes[-1] * (1 + ret)]))[-1]

  async def minutely_update(self):
    self.fetch = asyncio.create_task(self.fetch_current_risk())
    while True :
      try :
        await self.trade()
      except asyncio.CancelledError:
        break
      except Exception as e:
        logger.error(f"minutely_update {e}")
      await asyncio.sleep(self.UPDATE_SECONDS)

  def log_current_risk(self, venue):
    current_risk = 0
    current_risk_type = 'XBT'

    for sym in self.VENUES[venue]:
      if sym.endswith('USD') :
        current_risk = self.VENUES[venue][sym]['current_risk']
        current_risk_type = 'XBT'
      else:
        current_risk = self.VENUES[venue][sym]['current_risk']
        current_risk_type = 'USDT'

      orders = self.VENUES[venue][sym]['orders']
      logger.info(f'{venue} - {sym} current risk: {current_risk} {current_risk_type}, orders: {orders}')

  async def fetch_current_risk(self):
    while True :
      # Clear orders, sometimes there is a bad state in bitmex and/or profitview
      for venue in self.VENUES:
        for sym in self.VENUES[venue]:
          self.cancel_order(venue, sym=sym)
          self.VENUES[venue][sym]['orders'] = {'bid':{}, 'ask':{}}

      for venue in self.VENUES:
        positions=self.fetch_positions(venue)
        if positions :
          for x in positions['data']:
            if x['sym'] in self.VENUES[venue]:
              self.VENUES[venue][x['sym']]['current_risk'] = x['pos_size']

        orders=self.fetch_open_orders(venue)
        if orders :
          for x in orders['data']:
            if x['sym'] in self.VENUES[venue]:
              key = 'bid' if x['side'] == 'Buy' else 'ask'
              self.VENUES[venue][x['sym']]['orders'][key][x['order_id']] = x

        self.log_current_risk(venue)
      # Every 30m
      await asyncio.sleep(30*60)

  def remove_duplicates(self, arr):
    unique_items = list(set(arr))
    return unique_items

  def round_value(self, x, tick, decimals=0):
    return np.round(tick * np.round(x / tick), decimals)

  def orders_intent(self, sym):
    orders = {'bids': {}, 'asks': {}}
    if sym['mode'] == 'GRID' :
      tob_bid, tob_ask = sym['tob']
      times, closes = zip(*sorted(sym['candles'].items())[-self.LOOKBACK:])
      if len(sym['candles']) > 10 * self.LOOKBACK :
        sym['candles'] = dict(zip(times, closes))
      closes = list(filter(None,closes))
      X = np.linspace(-0.2, 0.2, self.LOOKBACK)
      Y = [self.hypo_rsi(closes, x) for x in X]
      func = interp1d(Y, X, kind='cubic', fill_value='extrapolate')

      orders = {
        'bids': [np.min([tob_bid, self.round_value(0.5 * round(closes[-1] * (1 + float(func(x))) / 0.5,4),sym['price_precision'], sym['price_decimals'])]) for x in self.GRID_BIDS],
        'asks': [np.max([tob_ask, self.round_value(0.5 * round(closes[-1] * (1 + float(func(x))) / 0.5,4),sym['price_precision'], sym['price_decimals'])]) for x in self.GRID_ASKS]
      }
      orders['bids'] = self.remove_duplicates(orders['bids'])
      orders['asks'] = self.remove_duplicates(orders['asks'])

    logger.info('sym:' + sym['sym'] + json.dumps(orders))
    return orders

  def order_exists(self, price, orders):
    for order_id, order in orders.items() :
      if order['order_price'] == price :
        return order_id
    return None

  # Place orders against a price list, minimizing API calls
  # * If an order with same price exists, it is not updated
  # * If there are existing orders, they get amended ( faster call )
  # * If there are more prices than available orders, new orders get created
  # * If there are more available orders than prices, the excess orders get deleted
  def limit_orders(self, is_bid, venue, sym, tob, prices, size_multiplier = 1) :
    key = 'bid' if is_bid else 'ask'
    sign = 1 if is_bid else -1
    side = 'Buy' if is_bid else 'Sell'
    opposite_direction = 'SHORT' if is_bid else 'LONG'

    # Dict to hold orders to be consumed for amend, cancel or do nothing
    orders = sym['orders'][key].copy()
    # logger.info(f'limit_orders start, {orders=}')

    # If we did not reach max_risk, or we have an open position of opposite direction of the order side
    if (abs(sym['current_risk']) < sym['max_risk']) or ((sign * sym['current_risk']) <= 0) :
      if self.SHUT_IT_DOWN :
        if self.GRACEFUL_SHUTDOWN :
          price = tob
          execInst = 'Close,ParticipateDoNotInitiate'
        else :
          price = tob
          execInst = 'Close'

        for attempt in range(10):
          try:
            if self.ACTIVE:
              response = self.call_endpoint(
                venue,
                'order',
                'private',
                method = 'POST',
                params = {
                  'symbol': sym['sym'],
                  'side': side,
                  'price': price,
                  'ordType': 'Limit',
                  'execInst': execInst,
                  'text': 'Sent from ProfitView.net'
                }
              )
              if response["error"] is not None :
                logger.error(f"POST order {response['error']}")
                time.sleep(0.5)
                continue
              if attempt > 0 :
                logger.info(f"POST order success after {attempt=}")
          except Exception as e:
            logger.error(f"POST order {e}")
            time.sleep(0.5)
          else:
            break

      else :
        # If there is a current open position in the opposite direction, multiply the order size
        multiplier = 1
        if (sign * sym['current_risk']) <= 0 :
          multiplier = sym.get('multiplier', 1)

        # If we are enforcing a trade direction, and if we are in the opposite direction order type, we have to reduce only
        reduce_only = False
        reduce_size = 0
        if sym['direction'] == opposite_direction :
          # No open position, clear prices
          if int(sym['current_risk']) == 0 :
            prices=[]
          execInst = 'ParticipateDoNotInitiate,ReduceOnly'
          reduce_only = True
          # Total reduce_size is open position + sign * orders remain_size, need to keep track for reduce_only
          reduce_size = sym['current_risk']
          if orders :
            for order_id, order in orders.items() :
              reduce_size = round(reduce_size + sign * order['remain_size'], 1)
        else:
          execInst = 'ParticipateDoNotInitiate'

        # First cycle, find all orders that already have the same price as prices
        # * Use array copy to be able to remove found prices from original array
        if prices :
          for price in prices[:]:
            if orders :
              # Find if there is already an order with same price
              order_id = self.order_exists(price, orders)
              if order_id :
                # The price is present, we don't need it in next cycles
                prices.remove(price)
                # The order has been "consumed", remove from the temporary dict
                del orders[order_id]
            else :
              break

        # Second cycle, amend existing orders as long as we have enough active orders
        if prices :
          for price in prices[:]:
            if orders :
              # Get first order_id available
              order_id = next(iter(orders))
              # Amend the order
              for attempt in range(10):
                try:
                  if self.ACTIVE:
                    response = self.call_endpoint(
                      venue,
                      'order',
                      'private',
                      method = 'PUT',
                      params = {
                        'orderID': order_id,
                        'price': price,
                        'text': 'Sent from ProfitView.net'
                      }
                    )
                    if response["error"] is not None :
                      if ('Filled' in response['error']) or ('Canceled' in response['error']) or ('Invalid orderID' in response['error']) or ('Invalid amend' in response['error']):
                        del orders[order_id]
                        break
                      logger.error(f"PUT order {response['error']}")
                      time.sleep(0.5)
                      continue
                    if attempt > 0 :
                      logger.info(f"PUT order success after {attempt=}")
                  prices.remove(price)
                  del orders[order_id]
                except Exception as e:
                  if ('Filled' in str(e)) or ('Canceled' in str(e)) or ('Invalid orderID' in str(e)) or ('Invalid amend' in str(e)):
                    del orders[order_id]
                    break
                  logger.error(f"PUT order {e}")
                  time.sleep(0.5)
                else:
                  break
            else :
              break

        # There are more prices but no orders available left, create new orders
        if prices :
          for price in prices:
            # In reduce only, we don't want to send an order that would put the risk in the wrong direction
            # * They get cancelled anyway
            if reduce_only :
              if (sign * int(reduce_size + sign * sym['order_size'] * multiplier * size_multiplier)) > 0 :
                break
            for attempt in range(10):
              try:
                if self.ACTIVE:
                  response = self.call_endpoint(
                    venue,
                    'order',
                    'private',
                    method = 'POST',
                    params = {
                      'symbol': sym['sym'],
                      'side': side,
                      'orderQty': sym['order_size'] * multiplier * size_multiplier,
                      'price': price,
                      'ordType': 'Limit',
                      'execInst': execInst,
                      'text': 'Sent from ProfitView.net'
                    }
                  )
                  if response["error"] is not None :
                    logger.error(f"POST order {response['error']}")
                    time.sleep(0.5)
                    continue
                  if attempt > 0 :
                    logger.info(f"POST order success after {attempt=}")
                reduce_size = round(reduce_size + sign * sym['order_size'] * multiplier * size_multiplier, 1)
              except Exception as e:
                logger.error(f"POST order {e}")
                time.sleep(0.5)
              else:
                break

        # TODO calculate open orders + current_risk and cancel orders that would let go above max_risk

        # There are more orders left but no prices, cancel the orders
        if orders :
          for order_id, _ in orders.items() :
            # Cancel the order
            for attempt in range(10):
              try:
                if self.ACTIVE:
                  response = self.call_endpoint(
                    venue,
                    'order',
                    'private',
                    method='DELETE',
                    params={
                      'orderID': order_id,
                      'text': 'Sent from ProfitView.net'
                    }
                  )
                  if response["error"] is not None :
                    logger.error(f"DELETE order {response['error']}")
                    time.sleep(0.5)
                    continue
                  if attempt > 0 :
                    logger.info(f"DELETE order success after {attempt=}")
              except Exception as e:
                logger.error(f"DELETE order {e}")
                time.sleep(0.5)
              else:
                break

  def taker_order(self, is_bid, venue, sym, price, size_multiplier = 1) :
    sign = 1 if is_bid else -1
    side = 'Buy' if is_bid else 'Sell'

    if (abs(sym['current_risk']) < sym['max_risk']) or ((sign * sym['current_risk']) <= 0) :
      for attempt in range(10):
        try:
          if self.ACTIVE:
            response = self.call_endpoint(
              venue,
              'order',
              'private',
              method = 'POST',
              params = {
                'symbol': sym['sym'],
                'side': side,
                'orderQty': sym['order_size'] * size_multiplier,
                'ordType': 'Market',
                'text': 'Sent from ProfitView.net'
              }
            )
            if response["error"] is not None :
              logger.error(f"POST order {response['error']}")
              time.sleep(0.5)
              continue
            if attempt > 0 :
              logger.info(f"POST order success after {attempt=}")
        except Exception as e:
          logger.error(f"POST order {e}")
          time.sleep(0.5)
        else:
          break

      self.limit_orders( is_bid=is_bid, venue=venue, sym=sym, tob=price, prices=[price], size_multiplier=size_multiplier)

  async def trade(self):
    for venue in self.VENUES:
      for sym in self.VENUES[venue]:
        self.compute_mode(self.VENUES[venue][sym])
        logger.info(f'sym: {sym} {self.VENUES[venue][sym]["mode"]}')
        tob_bid, tob_ask =  self.VENUES[venue][sym]['tob']

        if self.VENUES[venue][sym]['mode'] == 'GRID' :
          await self.update_limit_orders(venue, self.VENUES[venue][sym])
          await asyncio.sleep(1)
        elif self.VENUES[venue][sym]['mode'] == 'TAKER_LONG' :
          if np.isnan(tob_bid) :
            continue
          self.taker_order(is_bid=True, venue=venue, sym=self.VENUES[venue][sym], price=tob_bid, size_multiplier=self.ORDER_MULTIPLIER )
        elif self.VENUES[venue][sym]['mode'] == 'REDUCE_LONG' and self.VENUES[venue][sym]['current_risk'] < 0 :
          if np.isnan(tob_bid) :
            continue
          if self.REDUCE_TAKER :
            self.taker_order(is_bid=True, venue=venue, sym=self.VENUES[venue][sym], price=tob_bid, size_multiplier=self.ORDER_MULTIPLIER )
          else :
            self.limit_orders(is_bid=True, venue=venue, sym=self.VENUES[venue][sym], tob=tob_bid, prices=[tob_bid], size_multiplier=self.ORDER_MULTIPLIER )
        elif self.VENUES[venue][sym]['mode'] == 'TAKER_SHORT' :
          if np.isnan(tob_ask) :
            continue
          self.taker_order(is_bid=False, venue=venue, sym=self.VENUES[venue][sym], price=tob_ask, size_multiplier=self.ORDER_MULTIPLIER )
        elif self.VENUES[venue][sym]['mode'] == 'REDUCE_SHORT' and self.VENUES[venue][sym]['current_risk'] > 0 :
          if np.isnan(tob_ask) :
            continue
          if self.REDUCE_TAKER :
            self.taker_order(is_bid=False, venue=venue, sym=self.VENUES[venue][sym], price=tob_ask, size_multiplier=self.ORDER_MULTIPLIER )
          else :
            self.limit_orders(is_bid=False, venue=venue, sym=self.VENUES[venue][sym], tob=tob_ask, prices=[tob_ask], size_multiplier=self.ORDER_MULTIPLIER )

  async def update_limit_orders(self, venue, sym):
    tob_bid, tob_ask =  sym['tob']
    if(np.isnan(tob_bid) or np.isnan(tob_ask)):
      return

    intent = self.orders_intent(sym)

    # Buy orders
    self.limit_orders( is_bid=True, venue=venue, sym=sym, tob=tob_bid, prices=intent['bids'] )
    # Sell orders
    self.limit_orders( is_bid=False, venue=venue, sym=sym, tob=tob_ask, prices=intent['asks'] )

  @debounce(5)
  def update_tob_order(self, venue, sym) :
    tob_bid, tob_ask = sym['tob']

    # We expect 1 order only to exist, verify if it is bid or ask
    if sym['tob_is_bid'] :
      tob = tob_bid - sym['price_spread']
    else :
      tob = tob_ask + sym['price_spread']

    logger.info(f'sym: {sym["sym"]} Update tob, {tob=} is_bid={sym["tob_is_bid"]}')

    # Create or update the order with the right side and tob value
    self.limit_orders( is_bid=sym['tob_is_bid'], venue=venue, sym=sym, tob=tob, prices=[tob] )
    # Delete other side orders
    self.limit_orders( is_bid=not sym['tob_is_bid'], venue=venue, sym=sym, tob=tob, prices=[] )

  def reverse_tob_order(self, venue, sym, previous_order_id) :

    is_filled = False
    for attempt in range(10):
      try:
        response = self.call_endpoint(
          venue,
          'order',
          'private',
          method = 'GET',
          params = {
            'filter' : json.dumps({
              'orderID': previous_order_id,
            }),
            'count': 1,
            'text': 'Sent from ProfitView.net'
          }
        )
        if response["error"] is not None :
          if 'Filled' in response['error'] :
            is_filled = True
            break
          logger.error(f"GET order {response['error']}")
          time.sleep(0.5)
          continue
        if attempt > 0 :
          logger.info(f"GET order success after {attempt=}")
        if response["data"] :
          order = response["data"][0]
          if order["ordStatus"] == "Filled" :
            is_filled = True
      except Exception as e:
        if 'Filled' in str(e) :
          is_filled = True
          break
        logger.error(f"GET order {e}")
        time.sleep(0.5)
      else:
        break

    if is_filled :
      sym['tob_is_bid'] = not sym['tob_is_bid']

      self.update_tob_order(venue=venue, sym=sym)

    logger.info(f'sym: {sym["sym"]} Reverse tob, {is_filled=} is_bid={sym["tob_is_bid"]}')

  @property
  def time_bin_now(self):
    return self.candle_bin(self.epoch_now, self.LEVEL)

  def last_closes(self, sym):
    start_time = self.time_bin_now - self.LOOKBACK * self.time_step
    times = [start_time + (i + 1) * self.time_step for i in range(self.LOOKBACK)]
    closes = [sym['candles'].get(x, np.nan) for x in times]
    return np.array(pd.Series(closes).ffill())

  def update_signal(self, sym):
    last_closes = self.last_closes(sym)
    macd, signal, hist = MACD(last_closes)
    sym['macd'] = (hist[-1]/np.nanmean(last_closes)) * 10000
    # try:
    #   cubic = CubicSpline(range(self.CUBIC_N), hist[-self.CUBIC_N:])
    #   sym['macd'] = float(cubic(self.CUBIC_N-1, 1))
    # except Exception as e:
    #   logger.error(f'unable to update signal - {e}', exc_info=True)

  def compute_mode(self, sym):
    if sym['mode'] == 'TOB' :
      return
    previous_macd = sym['macd']
    self.update_signal(sym)
    logger.info(sym['sym'] + ': prev: ' + str(round(previous_macd, 4)) + ' curr: ' + str(round(sym['macd'], 4)))
    if np.isnan(previous_macd) :
      return

    if (sym['macd'] > self.MACD_RANGE) and (sym['macd'] > previous_macd) :
      sym['mode'] = 'TAKER_LONG'
    elif (sym['macd'] < -self.MACD_RANGE) and (sym['macd'] < previous_macd) :
      sym['mode'] = 'TAKER_SHORT'
    elif sym['mode'] == 'TAKER_LONG' and (sym['macd'] < previous_macd) :
      sym['mode'] = 'REDUCE_SHORT'
    elif sym['mode'] == 'TAKER_SHORT' and (sym['macd'] > previous_macd) :
      sym['mode'] = 'REDUCE_LONG'
    elif (sym['mode'] == 'REDUCE_SHORT' or sym['mode'] == 'REDUCE_LONG') and (abs(sym['current_risk']) <= sym['order_size'] or (sym['macd'] > -self.MACD_RANGE and sym['macd'] < self.MACD_RANGE)) :
      sym['mode'] = 'GRID'

  def trade_update(self, src, sym, data):
    if not self.INIT_COMPLETE :
      return
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['candles'][self.candle_bin(data['time'], self.LEVEL)] = data['price']

  def quote_update(self, src, sym, data):
    if not self.INIT_COMPLETE :
      return
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        tob_bid, tob_ask = self.VENUES[venue][sym]['tob']
        self.VENUES[venue][sym]['tob'] = (data['bid'][0], data['ask'][0])
        if (mid := np.mean(self.VENUES[venue][sym]['tob'])) != self.VENUES[venue][sym]['mid']:
          self.VENUES[venue][sym]['mid'] = mid
        if self.VENUES[venue][sym]['mode'] == 'TOB' :
          if (tob_bid != data['bid'][0]) or (tob_ask != data['ask'][0]) :
            self.update_tob_order(venue=venue, sym=self.VENUES[venue][sym])

  def order_update(self, src, sym, data):
    if not self.INIT_COMPLETE :
      return
    venue = data['venue']
    key = 'bid' if data['side'] == 'Buy' else 'ask'
    if venue in self.VENUES :
      if sym in self.VENUES[venue]:
        # Found the order
        if data['order_id'] in self.VENUES[venue][sym]['orders'][key] :
          # Completed/Cancelled
          if data.get('remain_size') == 0 :
            self.VENUES[venue][sym]['orders'][key].pop(data['order_id'], None)
            # Handle tob mode
            if self.VENUES[venue][sym]['mode'] == 'TOB' :
              # Handle inversion: place bid if order was Sell, place ask if order was Buy
              self.reverse_tob_order(venue=venue, sym=self.VENUES[venue][sym], previous_order_id=data['order_id'])
          # Update
          else :
            self.VENUES[venue][sym]['orders'][key][data['order_id']].update(data)
        # New order
        else :
          # Not cancelled
          if data.get('remain_size') != 0 :
            self.VENUES[venue][sym]['orders'][key][data['order_id']] = data

  def fill_update(self, src, sym, data):
    if not self.INIT_COMPLETE :
      return
    venue = data['venue']
    sign = 1 if data['side'] == 'Buy' else -1
    if venue in self.VENUES :
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['current_risk'] = round(self.VENUES[venue][sym]['current_risk'] + sign * data['fill_size'], 1)

  @http.route
  def get_button(self, data):
    logger.info(("get_button", data))
    return "get_button"

  @http.route
  def post_button(self, data):
    logger.info("post_button")
    logger.info(f"UPDATE_SECONDS - before: {self.UPDATE_SECONDS}")
    logger.info(f"GRID_BIDS - before: {self.GRID_BIDS}")
    logger.info(f"GRID_ASKS - before: {self.GRID_ASKS}")
    logger.info(f"LOOKBACK - before: {self.LOOKBACK}")
    logger.info(f"LEVEL - before: {self.LEVEL}")
    output = []
    for (p, v) in data.items():
      v = v.strip()
      if v[0]+v[-1] == '()':  # eg GRID_BIDS int tuple as string
        v = tuple(int(c.strip()) for c in v[1:-1].split(','))
      setattr(self, p, v)  # No validation!
      output.append([p, v])
    logger.info(f"UPDATE_SECONDS - after: {self.UPDATE_SECONDS}")
    logger.info(f"GRID_BIDS - after: {self.GRID_BIDS}")
    logger.info(f"GRID_ASKS - after: {self.GRID_ASKS}")
    logger.info(f"LOOKBACK - after: {self.LOOKBACK}")
    logger.info(f"LEVEL - after: {self.LEVEL}")
    return output  # Just returning what's passed as an example

  @http.route
  def get_toggle_bot(self, data):  # Possibly toggle order entry
    self.ACTIVE = not self.ACTIVE
    logger.info("Active" if self.ACTIVE else "Inactive")
    return "get_toggle_bot"

  # @http.route
  # def get_health(self, data):
  #     if time.time() - self.last_order_at < 180:
  #         return time.time() - self.last_order_at
  #     return Exception
