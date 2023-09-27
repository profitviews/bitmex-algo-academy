# Note: this file is to be used within profitview.net/trading/bots

from profitview import Link, http, logger

import json
import numpy as np
import pandas as pd
import scipy
import talib
from scipy.interpolate import interp1d
from talib import RSI
import threading
import time


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



class Trading(Link):

    def __init__(self):
        super().__init__()
        # ALGO PARAMS
        self.src = 'BitMEX'                         # exchange name
		self.SHUT_IT_DOWN = False
		self.GRACEFUL_SHUTDOWN = True
		self.venues = {
			'account1': {
				'XBTUSDT' : {
					'sym': 'XBTUSDT',
					'grid_size': 400000,
					'candles': {},
					'tob': (np.nan, np.nan),
					'max_risk': 4000000,
					'current_risk': 0,
					'price_precision': 0.5,
					'price_decimals': 1,
					'direction': 'FLAT'
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
					'grid_size': 20,
					'candles': {},
					'tob': (np.nan, np.nan),
					'max_risk': 400,
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
					'grid_size': 500000,
					'candles': {},
					'tob': (np.nan, np.nan),
					'max_risk': 10000000,
					'current_risk': 0,
					'price_precision': 0.1,
					'price_decimals': 1,
					'price_precision': 0.05,
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
        self.on_start()

	def on_start(self):
		for venue in self.venues:
			for sym in self.venues[venue]:
    			candles = self.fetch_candles(venue, sym, level='1m')
				self.venues[venue][sym]['candles'] = {x['time']: x['close'] for x in candles['data']} | self.venues[venue][sym]['candles']

    	self.minutely_update()

	def hypo_rsi(self, closes, ret):
		return RSI(np.append(closes, [closes[-1] * (1 + ret)]))[-1]

	def minutely_update(self):
		self.fetch_current_risk()
		self.update_limit_orders()
        threading.Timer(61 - self.second, self.minutely_update).start()

	def log_current_risk(self, venue):
		current_risk_usdt = 0
		current_risk_xbt = 0
		for sym in self.venues[venue]:
			if(sym.endswith('USD')):
				current_risk_xbt = self.venues[venue][sym]['current_risk']
			else:
				current_risk_usdt = self.venues[venue][sym]['current_risk']
		logger.info('\n '+ venue + ' current risk:' + json.dumps({
			'XBT': current_risk_xbt,
			'USDT': current_risk_usdt
		}))

    def fetch_current_risk(self):
		for venue in self.venues:
			for x in self.fetch_positions(venue)['data']:
				if x['sym'] in self.venues[venue]:
					self.venues[venue][x['sym']]['current_risk'] = x['pos_size']
			#self.log_current_risk(venue)


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
			'bids': [np.min([tob_bid, self.round_value(0.5 * round(closes[-1] * (1 + float(func(x))) / 0.5,4),sym['price_precision'], sym['price_decimals'])]) for x in (40, 30, 20)],
			'asks': [np.max([tob_ask, self.round_value(0.5 * round(closes[-1] * (1 + float(func(x))) / 0.5,4),sym['price_precision'], sym['price_decimals'])]) for x in (60, 70, 80)]
		}
		orders['bids'] = self.remove_duplicates(orders['bids'])
		orders['asks'] = self.remove_duplicates(orders['asks'])

		logger.info('sym:' + sym['sym'] + json.dumps(orders))
		return orders



    @debounce(1)
    def update_limit_orders(self):
		for venue in self.venues:
			for index, sym in enumerate(self.venues[venue]):
				tob_bid, tob_ask =  self.venues[venue][sym]['tob']
				if(np.isnan(tob_bid) or np.isnan(tob_ask)):
					return
				intent = self.orders_intent(self.venues[venue][sym])
				bids = intent['bids']
				asks = intent['asks']
				#cancel all current orders
				self.cancel_order(venue, sym=sym)
				if(abs(self.venues[venue][sym]['current_risk']) <  self.venues[venue][sym]['max_risk'] or self.venues[venue][sym]['current_risk'] <= 0):
					# If I have a current open position in the opposite direction, double the order size
					multiplyer = 1
					if(self.venues[venue][sym]['current_risk'] <= 0):
						multiplyer = 1
					if(self.venues[venue][sym]['direction'] == 'SHORT'):
						execInst = 'ParticipateDoNotInitiate,ReduceOnly'
					else:
						execInst = 'ParticipateDoNotInitiate'

					for bid in bids:
						if(self.SHUT_IT_DOWN and self.GRACEFUL_SHUTDOWN):
							bid = tob_bid
							execInst = 'Close'
						elif(self.SHUT_IT_DOWN and not self.GRACEFUL_SHUTDOWN):
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
									'orderQty': self.venues[venue][sym]['grid_size'] * multiplyer,
									'price': bid,
									'ordType': 'Limit',
									'execInst': execInst,
									'text': 'Sent from ProfitView.net'
							})
						except Exception as e:
							logger.error(e)

				if(abs(self.venues[venue][sym]['current_risk']) <  self.venues[venue][sym]['max_risk'] or  self.venues[venue][sym]['current_risk'] >= 0):
					# If I have a current open position in the opposite direction, double the order size
					multiplyer = 1
					if(self.venues[venue][sym]['current_risk'] >= 0):
						multiplyer = 1
					if(self.venues[venue][sym]['direction'] == 'LONG'):
						execInst = 'ParticipateDoNotInitiate,ReduceOnly'
					else:
						execInst = 'ParticipateDoNotInitiate'
					for ask in asks:
						if(self.SHUT_IT_DOWN and self.GRACEFUL_SHUTDOWN):
							bid = tob_ask
							execInst = 'Close'
						elif(self.SHUT_IT_DOWN and not self.GRACEFUL_SHUTDOWN):
							bid = tob_ask
							execInst = 'Close,ParticipateDoNotInitiate'
						try:
							self.call_endpoint(
								venue,
								'order',
								'private',
								method='POST', params={
									'symbol': sym,
									'side': 'Sell',
									'orderQty': self.venues[venue][sym]['grid_size'] * multiplyer,
									'price': ask,
									'ordType': 'Limit',
									'execInst': execInst,
									'text': 'Sent from ProfitView.net'
								})
						except Exception as e:
							logger.error(e)
            	time.sleep(1)

    def trade_update(self, src, sym, data):
		for venue in self.venues:
			if sym in self.venues[venue]:
				self.venues[venue][sym]['candles'][self.candle_bin(data['time'], '1m')] = data['price']

	def quote_update(self, src, sym, data):
        for venue in self.venues:
			if sym in self.venues[venue]:
            	self.venues[venue][sym]['tob'] = (data['bid'][0], data['ask'][0])
