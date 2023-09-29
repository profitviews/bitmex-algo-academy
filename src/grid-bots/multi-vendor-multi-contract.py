# 2023-09-29 16:54:26
# Note: this file is to be used within profitview.net/trading/bots
# pylint: disable=locally-disabled, import-self, import-error, missing-class-docstring, invalid-name, consider-using-dict-items

from profitview import Link, http, logger

import json
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from talib import RSI, MACD
import asyncio
import time

TIME_LOOKUP = {
  '1m':  60_000,
  '5m' : 60_000 * 5,
  '15m': 60_000 * 15,
  '1h':  60_000 * 60,
  '1d':  60_000 * 60 * 24,
}

# GARCH parameters
OMEGA = 1.605025e-08
ALPHA = 0.193613
BETA = 0.786155

class Trading(Link):
  UPDATE_SECONDS = 60
  SHUT_IT_DOWN = False
  GRACEFUL_SHUTDOWN = True
  GRID_BIDS = (40, 30, 20) # (40, 30, 20, 10)
  GRID_ASKS = (60, 70, 80) # (60, 70, 80, 90)
  LOOKBACK = 150
  LEVEL = '1m'
  SRC = 'bitmex'                         # exchange name as in the Glossary
  MAIN_VENUE='account1'
  VENUE_IDS = {
    'account1' : 0000000,
    'account2' : 0000000,
  }
  VENUES = {
      'account1': {
        'XBTUSDT' : {
          'order_size': 1_000 * 400,
          'max_risk': 1_000 * 400 * 10,                  # Means max 10 times the base order size
          'price_precision': 0.5,
          'size_precision': 1_000,
          'direction': 'FLAT',
          'multiplier': 1,
        },
        'XBTUSD' : {
          'order_size': 100 * 5,
          'max_risk': 100 * 5 * 160,
          'price_precision': 0.5,
          'size_precision': 100,
          'direction': 'FLAT',
          'multiplier': 1,
        },
        'ETHUSD' : {
          'order_size': 20,
          'max_risk': 20*20,
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
      }
    }

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
        self.VENUES[venue][sym]['macd'] = {'hist':np.nan, 'slope':np.nan}
        self.VENUES[venue][sym]['price_decimals'] = str(self.VENUES[venue][sym]['price_precision'])[::-1].find('.')
        self.VENUES[venue][sym]['size_precision'] = self.VENUES[venue][sym].get('size_precision', 1_000)

        candles = self.fetch_candles(self.MAIN_VENUE, sym, level=self.LEVEL)
        self.VENUES[venue][sym]['candles'] = {x['time']: x['close'] for x in candles['data']} | self.VENUES[venue][sym]['candles']

    self.fetch_current_risk()
    asyncio.run(self.minutely_update())

  def hypo_rsi(self, closes, ret):
    return RSI(np.append(closes, [closes[-1] * (1 + ret)]))[-1]

  async def minutely_update(self):
    while True :
      try :
        await self.update_limit_orders()
      except asyncio.CancelledError:
        break
      except Exception as e:
        logger.error(e)
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

  def fetch_current_risk(self):
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

  def remove_duplicates(self, arr):
    unique_items = list(set(arr))
    return unique_items

  def round_value(self, x, tick, decimals=0):
    return np.round(tick * np.round(x / tick), decimals)

  def orders_intent(self, sym):
    tob_bid, tob_ask = sym['tob']
    times, closes = zip(*sorted(sym['candles'].items())[-self.LOOKBACK:])
    if len(sym['candles']) > 10 * self.LOOKBACK :
      sym['candles'] = dict(zip(times, closes))
    closes = list(filter(None,closes))
    X = np.linspace(-0.2, 0.2, self.LOOKBACK)
    Y = [self.hypo_rsi(closes, x) for x in X]
    func = interp1d(Y, X, kind='cubic', fill_value='extrapolate')
    #logger.info(json.dumps({
    #	'sym': sym['sym'],
    #	'total': 0.5 * round(closes[-1] * (1 + float(func(60))) / 0.5),
    #	'close': closes[-1],
    #	'closeLength': len(closes),
    #	'func': (1 + float(func(60))),
    #	'tob': tob_ask,
    #	'final_closest_bid': np.max([tob_ask, 0.5 * round(closes[-1] * (1 + float(func(60))) / 0.5)]),
    #	'current_risk': sym['current_risk']
    #}))

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

  async def update_limit_orders(self):
    for venue in self.VENUES:
      # self.log_current_risk(venue)
      for sym in self.VENUES[venue]:
        tob_bid, tob_ask =  self.VENUES[venue][sym]['tob']
        if(np.isnan(tob_bid) or np.isnan(tob_ask)):
          continue

        intent = self.orders_intent(self.VENUES[venue][sym])
        bids = intent['bids']
        asks = intent['asks']

        # Dicts to hold orders to be consumed for amend, cancel or do nothing
        orders_bid = self.VENUES[venue][sym]['orders']['bid'].copy()
        orders_ask = self.VENUES[venue][sym]['orders']['ask'].copy()

        # Copy current_risk to keep track for ReduceOnly orders
        current_risk = self.VENUES[venue][sym]['current_risk']

        # Buy orders
        if (abs(current_risk) <  self.VENUES[venue][sym]['max_risk']) or (current_risk <= 0):
          if self.SHUT_IT_DOWN :
            if self.GRACEFUL_SHUTDOWN :
              bid = tob_bid
              execInst = 'Close,ParticipateDoNotInitiate'
            else :
              bid = tob_bid
              execInst = 'Close'

            try:
              self.call_endpoint(
                venue,
                'order',
                'private',
                method='POST',
                params={
                  'symbol': sym,
                  'side': 'Buy',
                  'price': bid,
                  'ordType': 'Limit',
                  'execInst': execInst,
                  'targetAccountId' : self.VENUE_IDS[venue],
                  'text': 'Sent from ProfitView.net'
                }
              )
            except Exception as e:
              logger.error(e)
          else :
            # If I have a current open position in the opposite direction, double the order size
            multiplier = 1
            reduce_only = False
            if current_risk <= 0 :
              multiplier = self.VENUES[venue][sym].get('multiplier', 1)
            if self.VENUES[venue][sym]['direction'] == 'SHORT' :
              if int(current_risk) == 0 :
                bids=[]
              execInst = 'ParticipateDoNotInitiate,ReduceOnly'
              reduce_only = True
            else:
              execInst = 'ParticipateDoNotInitiate'

            # First cycle, find all orders that already have the same price as bids
            # * Use array copy to be able to remove found bids from original array
            if bids :
              for bid in bids[:]:
                # We need available have orders
                if orders_bid :
                  # Find if there is already an order with same price
                  order_id = self.order_exists(bid, orders_bid)
                  if order_id :
                    # The bid is present, we don't need in next cycles
                    bids.remove(bid)
                    # The order has been "consumed", remove from the temporary dict
                    del orders_bid[order_id]
                else :
                  break

            # Second cycle, amend existing orders as long as we have enough active orders
            if bids :
              for bid in bids[:]:
                if orders_bid :
                  # Use an order, and remove from list of available at same time
                  order_id, _ = orders_bid.popitem()
                  # Amend the order
                  # self.amend_order(venue, order_id=order_id, price=bid)
                  try:
                    self.call_endpoint(
                      venue,
                      'order',
                      'private',
                      method='PUT',
                      params={
                        'orderID': order_id,
                        'price': bid,
                        'targetAccountId' : self.VENUE_IDS[venue],
                        'text': 'Sent from ProfitView.net'
                      }
                    )
                  except Exception as e:
                    logger.error(e)
                  # Bid used, we don't need in next cycles
                  bids.remove(bid)
                else :
                  break

            # There are more bid orders but no orders available left, create a new one
            if bids :
              for bid in bids:
                # In reduce only, we don't want to send an order that would put the risk in the wrong direction
                # * They get cancelled anyway
                if reduce_only :
                  current_risk += self.VENUES[venue][sym]['order_size'] * multiplier
                  if int(current_risk) > 0 :
                    break
                try:
                  self.call_endpoint(
                    venue,
                    'order',
                    'private',
                    method = 'POST',
                    params = {
                      'symbol': sym,
                      'side': 'Buy',
                      'orderQty': self.VENUES[venue][sym]['order_size'] * multiplier,
                      'price': bid,
                      'ordType': 'Limit',
                      'execInst': execInst,
                      'targetAccountId' : self.VENUE_IDS[venue],
                      'text': 'Sent from ProfitView.net'
                    }
                  )
                except Exception as e:
                  logger.error(e)

            # There are more orders left but no bids, cancel the orders
            if orders_bid :
              for order_id, _ in orders_bid.items() :
                # Cancel the order
                # self.cancel_order(venue, order_id=order_id)
                try:
                  self.call_endpoint(
                    venue,
                    'order',
                    'private',
                    method='DELETE',
                    params={
                      'orderID': order_id,
                      'targetAccountId' : self.VENUE_IDS[venue],
                      'text': 'Sent from ProfitView.net'
                    }
                  )
                except Exception as e:
                  logger.error(e)

        # Sell orders
        if (abs(current_risk) <  self.VENUES[venue][sym]['max_risk']) or (current_risk >= 0):
          if self.SHUT_IT_DOWN :
            if self.GRACEFUL_SHUTDOWN :
              bid = tob_ask
              execInst = 'Close,ParticipateDoNotInitiate'
            else :
              bid = tob_ask
              execInst = 'Close'

            try:
              self.call_endpoint(
                venue,
                'order',
                'private',
                method='POST',
                params={
                  'symbol': sym,
                  'side': 'Sell',
                  'price': bid,
                  'ordType': 'Limit',
                  'execInst': execInst,
                  'targetAccountId' : self.VENUE_IDS[venue],
                  'text': 'Sent from ProfitView.net'
                }
              )
            except Exception as e:
              logger.error(e)
          else :
            # If I have a current open position in the opposite direction, double the order size
            multiplier = 1
            reduce_only = False
            if current_risk >= 0 :
              multiplier = self.VENUES[venue][sym].get('multiplier', 1)
            if self.VENUES[venue][sym]['direction'] == 'LONG' :
              if int(current_risk) == 0 :
                asks=[]
              execInst = 'ParticipateDoNotInitiate,ReduceOnly'
              reduce_only = True
            else:
              execInst = 'ParticipateDoNotInitiate'

            if asks :
              for ask in asks[:]:
                if orders_ask :
                  order_id = self.order_exists(ask, orders_ask)
                  if order_id :
                    asks.remove(ask)
                    del orders_ask[order_id]
                else :
                  break

            if asks :
              for ask in asks[:]:
                if orders_ask :
                  order_id, _ = orders_ask.popitem()
                  # self.amend_order(venue, order_id=order_id, price=ask)
                  try:
                    self.call_endpoint(
                      venue,
                      'order',
                      'private',
                      method='PUT',
                      params={
                        'orderID': order_id,
                        'price': ask,
                        'targetAccountId' : self.VENUE_IDS[venue],
                        'text': 'Sent from ProfitView.net'
                      }
                    )
                  except Exception as e:
                    logger.error(e)
                  asks.remove(ask)
                else :
                  break

            if asks :
              for ask in asks:
                # In reduce only, we don't want to send an order that would put the risk in the wrong direction
                # * They get cancelled anyway
                if reduce_only :
                  current_risk -= self.VENUES[venue][sym]['order_size'] * multiplier
                  if int(current_risk) < 0 :
                    break
                try:
                  self.call_endpoint(
                    venue,
                    'order',
                    'private',
                    method='POST',
                    params={
                      'symbol': sym,
                      'side': 'Sell',
                      'orderQty': self.VENUES[venue][sym]['order_size'] * multiplier,
                      'price': ask,
                      'ordType': 'Limit',
                      'execInst': execInst,
                      'targetAccountId' : self.VENUE_IDS[venue],
                      'text': 'Sent from ProfitView.net'
                    }
                  )
                except Exception as e:
                  logger.error(e)

            # There are more orders left but no bids, cancel the orders
            if orders_ask :
              for order_id, _ in orders_ask.items() :
                # Cancel the order
                # self.cancel_order(venue, order_id=order_id)
                try:
                  self.call_endpoint(
                    venue,
                    'order',
                    'private',
                    method='DELETE',
                    params={
                      'orderID': order_id,
                      'targetAccountId' : self.VENUE_IDS[venue],
                      'text': 'Sent from ProfitView.net'
                    }
                  )
                except Exception as e:
                  logger.error(e)

        await asyncio.sleep(1)

  def trade_update(self, src, sym, data):
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['candles'][self.candle_bin(data['time'], self.LEVEL)] = data['price']
        # self.update_signal()

  def quote_update(self, src, sym, data):
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['tob'] = (data['bid'][0], data['ask'][0])
        if (mid := np.mean(self.VENUES[venue][sym]['tob'])) != self.VENUES[venue][sym]['mid']:
            self.VENUES[venue][sym]['mid'] = mid
            # self.update_limit_orders()

  def order_update(self, src, sym, data):
    venue = data['venue']
    key = 'bid' if data['side'] == 'Buy' else 'ask'
    if venue in self.VENUES :
      if sym in self.VENUES[venue]:
        # Found the order
        if data['order_id'] in self.VENUES[venue][sym]['orders'][key] :
          # Completed/Cancelled
          if data.get('remain_size') == 0 :
            self.VENUES[venue][sym]['orders'][key].pop(data['order_id'], None)
          # Update
          else :
            self.VENUES[venue][sym]['orders'][key][data['order_id']].update(data)
        # New order
        else :
          # Not cancelled
          if data.get('remain_size') != 0 :
            self.VENUES[venue][sym]['orders'][key][data['order_id']] = data

  def fill_update(self, src, sym, data):
    venue = data['venue']
    sign = 1 if data['side'] == 'Buy' else -1
    if venue in self.VENUES :
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['current_risk'] = round(self.VENUES[venue][sym]['current_risk'] + sign * data['fill_size'], 1)
        # self.update_limit_orders() # update limit orders on risk change

  # @http.route
  # def get_example(self, data):
  #     return data

  # @http.route
  # def post_example(self, data):
  #     return data

  # @http.route
  # def get_health(self, data):
  #     if time.time() - self.last_order_at < 180:
  #         return time.time() - self.last_order_at
  #     return Exception
