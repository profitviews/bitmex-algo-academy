# 2023-09-28 12:57:28
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

class Trading(Link):
  UPDATE_SECONDS = 60
  SHUT_IT_DOWN = False
  GRACEFUL_SHUTDOWN = True
  GRID_BIDS = (40, 30, 20)
  GRID_ASKS = (60, 70, 80)
  SRC = 'bitmex'                         # exchange name as in the Glossary
  VENUES = {
      'account1': {
        'XBTUSDT' : {
          'sym': 'XBTUSDT',
          'grid_size': 400000,                    # min is 1000 == 0.001 XBT
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 400000*10,                  # Means max 10 times the base order size
          'current_risk': 0,
          'price_precision': 0.5,
          'price_decimals': 1,
          'direction': 'FLAT',
          'multiplier': '1',
        },
        'XBTUSD' : {
          'sym': 'XBTUSD',
          'grid_size': 500,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 80000,
          'current_risk': 0,
          'price_precision': 0.5,
          'price_decimals': 1,
          'direction': 'FLAT'
        },
        'XBTU23' : {
          'sym': 'XBTU23',
          'grid_size': 400,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 8000,
          'current_risk': 0,
          'price_precision': 0.5,
          'price_decimals': 1,
          'direction': 'FLAT'
        },
        'XBTZ23' : {
          'sym': 'XBTZ23',
          'grid_size': 400,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 8000,
          'current_risk': 0,
          'price_precision': 0.5,
          'price_decimals': 1,
          'direction': 'FLAT'
        },
        'ETHUSD' : {
          'sym': 'ETHUSD',
          'grid_size': 20,                    # min is 1 Contract =~ 1.5 mXBT
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 20*20,                  # Means max 20 times the base order size
          'current_risk': 0,
          'price_precision': 0.05,
          'price_decimals': 2,
          'direction': 'FLAT'
        },
        'LINKUSD' : {
          'sym': 'LINKUSD',
          'grid_size': 200,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 4000,
          'current_risk': 0,
          'price_precision': 0.001,
          'price_decimals': 3,
          'direction': 'FLAT'
        },
        'XRPUSD': {
          'sym': 'XRPUSD',
          'grid_size': 100,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 2000,
          'current_risk': 0,
          'price_precision': 0.0001,
          'price_decimals': 4,
          'direction': 'FLAT'
        },
        'SOLUSDT' : {
          'sym': 'SOLUSDT',
          'grid_size': 500000,                    # min is 1000 == 0.1 SOL
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 500000*20,
          'current_risk': 0,
          'price_precision': 0.01,
          'price_decimals': 2,
          'direction': 'FLAT'
        },
        'ETHUSDT' : {
          'sym': 'ETHUSDT',
          'grid_size': 200000,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 2000000,
          'current_risk': 0,
          'price_precision': 0.05,
          'price_decimals': 2,
          'direction': 'FLAT'
        }
      },
      'account2': {
        'XBTUSD' : {
          'sym': 'XBTUSD',
          'grid_size': 400,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 300000,
          'current_risk': 0,
          'price_precision': 0.5,
          'price_decimals': 1,
          'direction': 'LONG'
        },
        'XBTU23' : {
          'sym': 'XBTU23',
          'grid_size': 400,
          'candles': {},
          'tob': (np.nan, np.nan),
          'max_risk': 30000,
          'current_risk': 0,
          'price_precision': 0.5,
          'price_decimals': 1,
          'direction': 'LONG'
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
      await self.update_limit_orders()
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
    #logger.info('\n' + json.dumps({
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

  async def update_limit_orders(self):
    for venue in self.VENUES:
      for sym in self.VENUES[venue]:
        tob_bid, tob_ask =  self.VENUES[venue][sym]['tob']
        if(np.isnan(tob_bid) or np.isnan(tob_ask)):
          continue

        #cancel all current orders
        self.cancel_order(venue, sym=sym)

        intent = self.orders_intent(self.VENUES[venue][sym])
        bids = intent['bids']
        asks = intent['asks']

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
              multiplier = self.VENUES[venue][sym].get('multiplier', 1)
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
              multiplier = self.VENUES[venue][sym].get('multiplier', 1)
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

        await asyncio.sleep(3)

  def trade_update(self, src, sym, data):
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['candles'][self.candle_bin(data['time'], '1m')] = data['price']

  def quote_update(self, src, sym, data):
    # logger.info('\n' + json.dumps(data))
    for venue in self.VENUES:
      if sym in self.VENUES[venue]:
        self.VENUES[venue][sym]['tob'] = (data['bid'][0], data['ask'][0])
