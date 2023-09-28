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
        self.src = 'BitMEX'
		self.venue =  'BitMEX'
		self.active_usdt_order_id = ''
		self.active_usdt_order_size = ''

		self.XBTUSDT = {
			'sym': 'XBTUSDT',
			'grid_size': 380000,
			'tob': (np.nan, np.nan),
			'max_risk': 380000*5,
			'current_risk': 0,
			'price_precision': 0.5,
			'price_decimals': 1,
			'direction': 'FLAT'
		}
		self.XBTUSD = {
			'sym': 'XBTUSD',
			'grid_size': 10000,
			'tob': (np.nan, np.nan),
			'max_risk': 10000*5,
			'current_risk': 0,
			'price_precision': 0.5,
			'price_decimals': 1,
			'direction': 'FLAT'
		}
        self.on_start()

	def on_start(self):
    	while (True):
			self.fetch_current_risk()
			self.update_limit_orders()
			time.sleep(2)

	def minutely_update(self):
		self.fetch_current_risk()
		self.update_limit_orders()
        threading.Timer(31 - self.second, self.minutely_update).start()

    def fetch_current_risk(self):
		self.XBTUSDT['current_risk'] = 0
		self.XBTUSD['current_risk'] = 0
		for x in self.fetch_positions(self.venue)['data']:
			if x['sym'] == 'XBTUSDT':
				self.XBTUSDT['current_risk'] = x['pos_size']
			if x['sym'] == 'XBTUSD':
				self.XBTUSD['current_risk'] = x['pos_size']

	def remove_duplicates(self, arr):
		unique_items = list(set(arr))
		return unique_items

	def round_value(self, x, tick, decimals=0):
		return np.round(tick * np.round(x / tick), decimals)

    def orders_intent(self):
		tob_bid, tob_ask = sym['tob']

		# check if I have a XBTUSDT position, If I do not.

		orders = {
			'bids': [np.min([tob_bid, self.round_value(0.5 * round(closes[-1] * (1 + float(func(x))) / 0.5,4),sym['price_precision'], sym['price_decimals'])]) for x in (40, 30, 20)],
			'asks': [np.max([tob_ask, self.round_value(0.5 * round(closes[-1] * (1 + float(func(x))) / 0.5,4),sym['price_precision'], sym['price_decimals'])]) for x in (60, 70, 80)]
		}
		orders['bids'] = self.remove_duplicates(orders['bids'])
		orders['asks'] = self.remove_duplicates(orders['asks'])

		logger.info('sym:' + sym['sym'] + json.dumps(orders))
		return orders



    def update_limit_orders(self):
		xbttob_bid, xbttob_ask = self.XBTUSD['tob']
		usdttob_bid, usdttob_ask = self.XBTUSD['tob']
		if(np.isnan(usdttob_bid) or np.isnan(usdttob_ask) or np.isnan(xbttob_bid) or np.isnan(xbttob_ask)):
			return

		# If I have a position that is partially filled. you need to get it fully filled, so just put it to the top of the book
		if(self.active_usdt_order_id != ''):
			price = usdttob_ask
			if(self.active_usdt_order_side == 'Buy'):
				price = usdttob_bid
			logger.info('amending order ' + self.active_usdt_order_id + ' to price' + price)
			self.amend_order(self.venue, order_id=self.active_usdt_order_id, price=price)
			return

		# check if I have an open position on XBTUSDT and XBTUSD, If I don't have an XBTUSDT position but do have a XBTUSD position, I need to close this XBTUSD position out asap
		self.cancel_order(self.venue, sym='XBTUSDT')
		self.cancel_order(self.venue, sym='XBTUSD')
		logger.info(json.dumps({
			'XBTUSDT': self.XBTUSDT['current_risk'],
			'XBTUSD': self.XBTUSD['current_risk']
		}))
		if(self.XBTUSDT['current_risk'] == 0 and self.XBTUSD['current_risk'] != 0):
			tob_bid, tob_ask = self.XBTUSD['tob']
			# check the side
			side = 'Buy'
			price = tob_ask
			if(self.XBTUSD['current_risk'] > 0):
				side = 'Sell'
				price = tob_bid
			self.call_endpoint(
				self.venue,
				'order',
				'private',
				method='POST',
				params={
					'symbol': 'XBTUSD',
					'side': side,
					'orderQty': self.XBTUSD['grid_size'],
					'ordType': 'Market',
					'text': 'Sent from ProfitView.net'
				}
			)
	   #If I have a position on XBTUSDT and I dont have a position on XBTUSD, then I need to open a position on XBTUSD asap
		elif(self.XBTUSD['current_risk'] == 0 and self.XBTUSDT['current_risk'] != 0):
			tob_bid, tob_ask = self.XBTUSD['tob']
			side = 'Buy'
			if(self.XBTUSDT['current_risk'] > 0):
				side = 'Sell'

			self.call_endpoint(
				self.venue,
				'order',
				'private',
				method='POST',
				params={
					'symbol': 'XBTUSD',
					'side': side,
					'orderQty': self.XBTUSD['grid_size'],
					'ordType': 'Market',
					'text': 'Sent from ProfitView.net'
				}
			)
		#If I have a position on both XBTUSDT and XBTUSD, I need to place a top of book limit order for XBTUSDT to try and close out the posiiton
		elif(self.XBTUSD['current_risk'] != 0 and self.XBTUSDT['current_risk'] != 0):
			tob_bid, tob_ask = self.XBTUSDT['tob']
			side = 'Buy'
			price = tob_bid
			if(self.XBTUSDT['current_risk'] > 0):
				side = 'Sell'
				price = tob_ask
			self.call_endpoint(
				self.venue,
				'order',
				'private',
				method='POST',
				params={
					'symbol': 'XBTUSDT',
					'side': side,
					'orderQty': self.XBTUSDT['grid_size'],
					'price': price,
					'ordType': 'Limit',
					'execInst': 'ParticipateDoNotInitiate',
					'text': 'Sent from ProfitView.net'
				}
			)
		#If I don't have a position on either XBTUSDT or XBTUSD, open two orders at the top of the books for XBTUSDT
		elif(self.XBTUSD['current_risk'] == 0 and self.XBTUSDT['current_risk'] == 0):
			tob_bid, tob_ask = self.XBTUSDT['tob']
			self.call_endpoint(
				self.venue,
				'order',
				'private',
				method='POST',
				params={
					'symbol': 'XBTUSDT',
					'side': 'Buy',
					'orderQty': self.XBTUSDT['grid_size'],
					'price': tob_bid,
					'ordType': 'Limit',
					'execInst': 'ParticipateDoNotInitiate',
					'text': 'Sent from ProfitView.net'
				}
			)
			self.call_endpoint(
				self.venue,
				'order',
				'private',
				method='POST',
				params={
					'symbol': 'XBTUSDT',
					'side': 'Sell',
					'orderQty': self.XBTUSDT['grid_size'],
					'price': tob_ask,
					'ordType': 'Limit',
					'execInst': 'ParticipateDoNotInitiate',
					'text': 'Sent from ProfitView.net'
				}
			)

	def quote_update(self, src, sym, data):
		if sym == 'XBTUSDT':
			self.XBTUSDT['tob'] = (data['bid'][0], data['ask'][0])
		if sym == 'XBTUSD':
			self.XBTUSD['tob'] = (data['bid'][0], data['ask'][0])

	def order_update(self, src, sym, data):
		if(sym == 'XBTUSDT' and data['remain_size'] > 0 and data['order_size'] != data['remain_size']):
			self.active_usdt_order_id = data['order_id']
			self.active_usdt_order_side = data['side']
		elif(sym == 'XBTUSDT'):
			self.active_usdt_order_id = ''
			self.active_usdt_order_side = ''

