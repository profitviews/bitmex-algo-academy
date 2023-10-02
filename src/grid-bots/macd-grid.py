# 2023-09-27 14:25:01
# Note: this file is to be used within profitview.net/trading/bots
# pylint: disable=locally-disabled, import-self, import-error, missing-class-docstring, invalid-name, consider-using-dict-items

from profitview import Link, http, logger

import json
import numpy as np
import pandas as pd
import scipy
import talib
from scipy.interpolate import interp1d
from talib import RSI
import asyncio
import time

#MODES: LONG_TAKER | REDUCE_MODE | SHORT_TAKER | GRID


class Trading(Link):
  UPDATE_SECONDS = 60
  MULTIPLIER = 1
  SHUT_IT_DOWN = False
  GRACEFUL_SHUTDOWN = True
  GRID_BIDS = (40, 30, 20)
  GRID_ASKS = (60, 70, 80)
  SRC = 'bitmex'                         # exchange name as in the Glossary
  VENUES = {
    'MrBath': {
      'XBTUSDT' : {
        'sym': 'XBTUSDT',
        'grid_size': 5000,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 5000*100,
        'current_risk': 0,
        'price_precision': 0.5,
        'price_decimals': 1,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'XBTUSD' : {
        'sym': 'XBTUSD',
        'grid_size': 300,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 300*100,
        'current_risk': 0,
        'price_precision': 0.5,
        'price_decimals': 1,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'XBTZ23' : {
        'sym': 'XBTZ23',
        'grid_size': 200,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 200*100,
        'current_risk': 0,
        'price_precision': 0.5,
        'price_decimals': 1,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'ETHUSD' : {
        'sym': 'ETHUSD',
        'grid_size': 10,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 10*100,
        'current_risk': 0,
        'price_precision': 0.05,
        'price_decimals': 2,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'LINKUSD' : {
        'sym': 'LINKUSD',
        'grid_size': 50,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 50*100,
        'current_risk': 0,
        'price_precision': 0.001,
        'price_decimals': 3,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'XRPUSD': {
        'sym': 'XRPUSD',
        'grid_size': 20,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 20*100,
        'current_risk': 0,
        'price_precision': 0.0001,
        'price_decimals': 4,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'SOLUSDT' : {
        'sym': 'SOLUSDT',
        'grid_size': 25000,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 25000*100,
        'current_risk': 0,
        'price_precision': 0.1,
        'price_decimals': 1,
        'price_precision': 0.05,
        'price_decimals': 2,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'ETHUSDT' : {
        'sym': 'ETHUSDT',
        'grid_size': 10000,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 10000*100,
        'current_risk': 0,
        'price_precision': 0.05,
        'price_decimals': 2,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      }
  	},
    'RunningDoge': {
      'XBTUSD' : {
        'sym': 'XBTUSD',
        'grid_size': 400,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 30000,
        'current_risk': 0,
        'price_precision': 0.5,
        'price_decimals': 1,
        'direction': 'LONG',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'XBTZ23' : {
        'sym': 'XBTZ23',
        'grid_size': 400,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 50000,
        'current_risk': 0,
        'price_precision': 0.5,
        'price_decimals': 1,
        'direction': 'LONG',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'ETHUSD' : {
        'sym': 'ETHUSD',
        'grid_size': 100,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 0,
        'current_risk': 0,
        'price_precision': 0.05,
        'price_decimals': 2,
        'direction': 'LONG',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'LINKUSD' : {
        'sym': 'LINKUSD',
        'grid_size': 200,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 0,
        'current_risk': 0,
        'price_precision': 0.001,
        'price_decimals': 3,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      },
      'XRPUSD': {
        'sym': 'XRPUSD',
        'grid_size': 100,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 0,
        'current_risk': 0,
        'price_precision': 0.0001,
        'price_decimals': 4,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      }
    },
    'maria': {
      'XBTUSDT' : {
        'sym': 'XBTUSDT',
        'grid_size': 5000,
        'candles': {},
        'tob': (np.nan, np.nan),
        'max_risk': 10000,
        'current_risk': 0,
        'price_precision': 0.5,
        'price_decimals': 1,
        'direction': 'FLAT',
		'macd': np.nan,
		'mode': 'GRID'
      }
    }
  }

  def __init__(self):
    super().__init__()
    self.on_start()

  def on_start(self):
    for venue in self.VENUES:
      for sym in self.VENUES[venue]:
        candles = self.fetch_candles(venue, sym, level='1m')
        self.VENUES[venue][sym]['candles'] = {x['time']: x['close'] for x in candles['data']} | self.VENUES[venue][sym]['candles']
    asyncio.run(self.minutely_update())

  def hypo_rsi(self, closes, ret):
    return RSI(np.append(closes, [closes[-1] * (1 + ret)]))[-1]

  async def minutely_update(self):
    while True :
      self.fetch_current_risk()
      await self.trade()
      await asyncio.sleep(self.UPDATE_SECONDS)

  @property
  def time_bin_now(self):
      return self.candle_bin(self.epoch_now, '1m')

  def last_closes(self, sym):
      start_time = self.time_bin_now - 100 * 60_000
      times = [start_time + (i + 1) * 60_000 for i in range(100)]
      closes = [sym['candles'].get(x, np.nan) for x in times]
      return np.array(pd.Series(closes).ffill())

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

      logger.info(f'\n{venue} - {sym} current risk: {current_risk} {current_risk_type}')

  def fetch_current_risk(self):
    for venue in self.VENUES:
      positions=self.fetch_positions(venue)
      if positions :
        for x in positions['data']:
          if x['sym'] in self.VENUES[venue]:
            self.VENUES[venue][x['sym']]['current_risk'] = x['pos_size']
      # self.log_current_risk(venue)

  def remove_duplicates(self, arr):
    unique_items = list(set(arr))
    return unique_items

  def round_value(self, x, tick, decimals=0):
    return np.round(tick * np.round(x / tick), decimals)

  def orders_intent(self, sym):
    tob_bid, tob_ask = sym['tob']
    times, closes = zip(*sorted(sym['candles'].items())[-100:])
    closes = list(filter(None,closes))
    X = np.linspace(-0.2, 0.2, 100)
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

  def update_signal(self, sym):
      macd, signal, hist = talib.MACD(self.last_closes(sym))
	  sym['macd'] = hist[-1] / self.last_closes(sym)[-1] * 100

  def compute_mode(self, sym):
	previous_macd = sym['macd']
	self.update_signal(sym)
	logger.info(sym['sym']+': prev: ' + str(round(previous_macd, 4)) + ' curr: ' + str(round(sym['macd'], 4)))

	if(np.isnan(previous_macd)):
	  return

	if(np.greater(sym['macd'], 0.1) and np.greater(sym['macd'], previous_macd)):
	  sym['mode'] = 'TAKER_LONG'
	  logger.info('TAKER_LONG')
    elif(np.greater(-0.1, sym['macd']) and sym['macd'] < previous_macd):
	  sym['mode'] = 'TAKER_SHORT'
	  logger.info('TAKER_SHORT')
	elif(sym['mode'] == 'TAKER_LONG' and sym['macd'] < previous_macd):
	  sym['mode'] = 'REDUCE'
	  logger.info('REDUCE')
	elif(sym['mode'] == 'TAKER_SHORT' and sym['macd'] > previous_macd):
	  sym['mode'] = 'REDUCE'
	  logger.info('REDUCE')
	elif(sym['mode'] == 'REDUCE' and (abs(sym['current_risk']) <= sym['grid_size'] or (sym['macd'] > -0.1 and sym['macd'] < 0.1))):
	  sym['mode'] = 'GRID'
	  logger.info('grid')


  async def trade(self):
	for venue in self.VENUES:
      for sym in self.VENUES[venue]:
		self.compute_mode(self.VENUES[venue][sym])
		logger.info("Mode: " + self.VENUES[venue][sym]['mode'])
		if(self.VENUES[venue][sym]['mode'] == 'GRID'):
		  await self.update_limit_orders(venue, sym)
	      await asyncio.sleep(3)
		elif((self.VENUES[venue][sym]['mode'] == 'TAKER_LONG') or (self.VENUES[venue][sym]['mode'] == 'REDUCE' and self.VENUES[venue][sym]['current_risk'] < 0)):
			await self.taker_long_orders(venue, sym)
		elif((self.VENUES[venue][sym]['mode'] == 'TAKER_SHORT') or (self.VENUES[venue][sym]['mode'] == 'REDUCE' and self.VENUES[venue][sym]['current_risk'] > 0)):
			await self.taker_short_orders(venue, sym)

  async def taker_long_orders(self, venue, sym):
	tob_bid, tob_ask = self.VENUES[venue][sym]['tob']
    if(np.isnan(tob_bid) or np.isnan(tob_ask)):
      return
	self.cancel_order(venue, sym=sym)
    if (abs(self.VENUES[venue][sym]['current_risk']) < self.VENUES[venue][sym]['max_risk']) or (self.VENUES[venue][sym]['current_risk'] <= 0):
	  # If taker_long, then market buy one and place a tob other
	  self.call_endpoint(
        venue,
        'order',
        'private',
        method='POST', params={
          'symbol': sym,
          'side': 'Buy',
		  'orderQty': self.VENUES[venue][sym]['grid_size'],
          'ordType': 'Market',
          'text': 'Sent from ProfitView.net'
        }
	  )

	  self.call_endpoint(
        venue,
        'order',
        'private',
        method='POST', params={
          'symbol': sym,
          'side': 'Buy',
          'price': tob_bid,
          'ordType': 'Limit',
		  'orderQty': self.VENUES[venue][sym]['grid_size'],
          'execInst': 'ParticipateDoNotInitiate',
          'text': 'Sent from ProfitView.net'
        }
	  )

  async def taker_short_orders(self, venue, sym):
	tob_bid, tob_ask = self.VENUES[venue][sym]['tob']
    if(np.isnan(tob_bid) or np.isnan(tob_ask)):
      return
	self.cancel_order(venue, sym=sym)
    if (abs(self.VENUES[venue][sym]['current_risk']) < self.VENUES[venue][sym]['max_risk']) or (self.VENUES[venue][sym]['current_risk'] >= 0):
	  # If taker_short, then market buy one and place a tob other
	  self.call_endpoint(
        venue,
        'order',
        'private',
        method='POST', params={
          'symbol': sym,
          'side': 'Sell',
          'ordType': 'Market',
		  'orderQty': self.VENUES[venue][sym]['grid_size'],
          'text': 'Sent from ProfitView.net'
        }
	  )

	  self.call_endpoint(
        venue,
        'order',
        'private',
        method='POST', params={
          'symbol': sym,
          'side': 'Sell',
          'price': tob_ask,
          'ordType': 'Limit',
		  'orderQty': self.VENUES[venue][sym]['grid_size'],
          'execInst': 'ParticipateDoNotInitiate',
          'text': 'Sent from ProfitView.net'
        }
	  )

  async def update_limit_orders(self, venue, sym):
    tob_bid, tob_ask = self.VENUES[venue][sym]['tob']
    if(np.isnan(tob_bid) or np.isnan(tob_ask)):
      return
    intent = self.orders_intent(self.VENUES[venue][sym])
    bids = intent['bids']
    asks = intent['asks']


    #cancel all current orders
    self.cancel_order(venue, sym=sym)

        # Buy orders
    if (abs(self.VENUES[venue][sym]['current_risk']) <  self.VENUES[venue][sym]['max_risk']) or (self.VENUES[venue][sym]['current_risk'] <= 0):
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
            method='POST', params={
              'symbol': sym,
              'side': 'Buy',
              'price': bid,
              'ordType': 'Limit',
              'execInst': execInst,
              'text': 'Sent from ProfitView.net'
            })
        except Exception as e:
          logger.error(e)
      else :
        # If I have a current open position in the opposite direction, double the order size
        multiplier = 1
        if(self.VENUES[venue][sym]['current_risk'] <= 0):
          multiplier = self.MULTIPLIER
        if(self.VENUES[venue][sym]['direction'] == 'SHORT'):
          execInst = 'ParticipateDoNotInitiate,ReduceOnly'
        else:
          execInst = 'ParticipateDoNotInitiate'
        for bid in bids:
          try:
            self.call_endpoint(
              venue,
              'order',
              'private',
              method = 'POST',
              params = {
                'symbol': sym,
                'side': 'Buy',
                'orderQty': self.VENUES[venue][sym]['grid_size'] * multiplier,
                'price': bid,
                'ordType': 'Limit',
                'execInst': execInst,
                'text': 'Sent from ProfitView.net'
              }
            )
          except Exception as e:
            logger.error(e)

    # Sell orders
    if (abs(self.VENUES[venue][sym]['current_risk']) <  self.VENUES[venue][sym]['max_risk']) or (self.VENUES[venue][sym]['current_risk'] >= 0):
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
            method='POST', params={
              'symbol': sym,
              'side': 'Sell',
              'price': bid,
              'ordType': 'Limit',
              'execInst': execInst,
              'text': 'Sent from ProfitView.net'
            })
        except Exception as e:
          logger.error(e)
      else :
        # If I have a current open position in the opposite direction, double the order size
        multiplier = 1
        if(self.VENUES[venue][sym]['current_risk'] >= 0):
          multiplier = self.MULTIPLIER
        if(self.VENUES[venue][sym]['direction'] == 'LONG'):
          execInst = 'ParticipateDoNotInitiate,ReduceOnly'
        else:
          execInst = 'ParticipateDoNotInitiate'
        for ask in asks:
          try:
            self.call_endpoint(
              venue,
              'order',
              'private',
              method='POST', params={
                'symbol': sym,
                'side': 'Sell',
                'orderQty': self.VENUES[venue][sym]['grid_size'] * multiplier,
                'price': ask,
                'ordType': 'Limit',
                'execInst': execInst,
                'text': 'Sent from ProfitView.net'
              })
          except Exception as e:
            logger.error(e)

  def trade_update(self, src, sym, data):
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['candles'][self.candle_bin(data['time'], '1m')] = data['price']

  def quote_update(self, src, sym, data):
    # logger.info('\n' + json.dumps(data))
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['tob'] = (data['bid'][0], data['ask'][0])
