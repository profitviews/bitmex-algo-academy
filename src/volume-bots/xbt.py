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

		self.XBTUSDT = {
			'sym': 'XBTUSDT',
			'order_size': 380000,
			'tob': (np.nan, np.nan),
			'current_risk': 0,
			'price_precision': 0.5,
			'price_decimals': 1
		}
		self.XBTUSD = {
			'sym': 'XBTUSD',
			'order_size': 10000,
			'tob': (np.nan, np.nan),
			'current_risk': 0,
			'price_precision': 0.5,
			'price_decimals': 1
		}
        self.on_start()

	def on_start(self):
    	while (True):
			self.fetch_current_risk()
			self.update_limit_orders()
			time.sleep(2)

    def fetch_current_risk(self):
		self.XBTUSDT['current_risk'] = 0
		self.XBTUSD['current_risk'] = 0
		for x in self.fetch_positions(self.venue)['data']:
			if x['sym'] == 'XBTUSDT':
				self.XBTUSDT['current_risk'] = x['pos_size']
			if x['sym'] == 'XBTUSD':
				self.XBTUSD['current_risk'] = x['pos_size']



	def round_value(self, x, tick, decimals=0):
		return np.round(tick * np.round(x / tick), decimals)



    def update_limit_orders(self):
		xbttob_bid, xbttob_ask = self.XBTUSD['tob']
		usdttob_bid, usdttob_ask = self.XBTUSD['tob']
		if(np.isnan(usdttob_bid) or np.isnan(usdttob_ask) or np.isnan(xbttob_bid) or np.isnan(xbttob_ask)):
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
			if(self.XBTUSD['current_risk'] > 0):
				side = 'Sell'
			self.call_endpoint(
				self.venue,
				'order',
				'private',
				method='POST',
				params={
					'symbol': 'XBTUSD',
					'side': side,
					'orderQty': abs(self.XBTUSD['current_risk']),
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
					'orderQty': self.round_value(abs(self.XBTUSDT['current_risk']) / 38, self.XBTUSD['price_precision'], self.XBTUSD['price_decimals']),
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
					'orderQty': abs(self.XBTUSDT['current_risk']),
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
					'orderQty': self.XBTUSDT['order_size'],
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


