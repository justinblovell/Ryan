#!/usr/bin/python3

import base64
import datetime
import hashlib
import hmac
import requests
import time
import random
import logging

from ratelimit import limits, sleep_and_retry
from requests.auth import AuthBase


# Copyright 2018, Justin B. Lovell, All rights reserved.
class CoinbaseExchangeAuth(AuthBase):

    def __init__(self, api_key, secret_key, passphrase):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    def __call__(self, request):
        timestamp = str(time.time())
        message = timestamp + request.method + request.path_url + (request.body or b'').decode()
        hmac_key = base64.b64decode(self.secret_key)
        signature = hmac.new(hmac_key, message.encode(), hashlib.sha256)
        signature_b64 = base64.b64encode(signature.digest()).decode()

        request.headers.update({
            'CB-ACCESS-SIGN': signature_b64,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        })
        return request


CURRENCY = 'BTC'
USD_KEY = 'USD'
PRODUCT_ID = CURRENCY + '-USD'
TRADE_DOLLAR_AMOUNT = 15.00
TIME_IN_FORCE_VALUE = 'GTT'
CANCEL_AFTER_DAY_VALUE = 'day'
CANCEL_AFTER_HOUR_VALUE = 'hour'
API_KEY = 'apikeygoeshere'
API_SECRET = 'apisecretgoeshere'
API_PASS = 'apipasswordgoeshere'
BASE_URL = 'https://api.gdax.com/'
ACCOUNTS_API_URL = BASE_URL + 'accounts/'
PRODUCT_TICKER_API_URL = BASE_URL + 'products/' + PRODUCT_ID + '/ticker'
ORDERS_URL = BASE_URL + 'orders'
FILLS_URL = BASE_URL + 'fills'
COIN_ACCOUNT_ID = 'COIN_ACCOUNT_ID'
USD_ACCOUNT_ID = 'USD_ACCOUNT_ID'
MINIMUM_DECREASE_AMOUNT = 3.00
MAXIMUM_DECREASE_AMOUNT = 300.00
INCREASE_AMOUNT = 10.00
RATE_LIMIT_QUOTA = 1
ONE_MINUTE = 60
ONE_SECOND = 1

auth = CoinbaseExchangeAuth(API_KEY, API_SECRET, API_PASS)


def retryer(max_retries=100, timeout=5):
    def wraps(func):
        request_exceptions = (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError
        )

        def inner(*args, **kwargs):
            encountered_exception = False
            for retry_attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                except request_exceptions:
                    encountered_exception = True
                    logging.error("Encountered network exception. Sleeping " + str(timeout * retry_attempt) + "seconds and then retrying")
                    time.sleep(timeout * retry_attempt)
                    continue
                else:
                    if not encountered_exception:
                        return result
                    else:
                        logging.info("Recovered from network exception after "+ str(timeout * retry_attempt) + " seconds and " + str(retry_attempt) + " retries")
                        return result
            else:
                logging.info("Exhausted network exception retries. Returning None.")
                return None
        return inner
    return wraps


def print_account_stats(accounts_response):
    logging.info("Account: " + str(accounts_response.json()["currency"]))
    logging.info("Balance: " + str(accounts_response.json()["available"]))


def print_ticker_stats(ticker_response):
    logging.info("BTC price: " + str(ticker_response.json()["price"]))


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_current_price():
    response = requests.get(PRODUCT_TICKER_API_URL, auth=auth)
    if response.status_code == 200:
        return response.json()['price']
    else:
        logging.warning("ticker api returned:" + str(response.status_code), str(response.content))
        return None


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_open_orders():
    params = {'status': 'open',
              'productId': PRODUCT_ID}

    response = requests.get(ORDERS_URL, auth=auth, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        logging.warning("orders api returned: " + str(response.status_code) + str(response.content))
        return None


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_orders():
    params = {'productId': PRODUCT_ID}
    response = requests.get(ORDERS_URL, auth=auth, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        logging.warning("orders api returned: " + str(response.status_code) + str(response.content))
        return list()


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_fill(order_id):
    fills_params = {
        'order_id': order_id,
        'product_id': PRODUCT_ID}
    response = requests.get(FILLS_URL, auth=auth, params=fills_params)
    if response.status_code == 200:
        return response.json()
    else:
        logging.warning("fills api returned: " + str(response.status_code) + str(response.content))
        return None


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_fills():
    fills_params = {
        'product_id': PRODUCT_ID}
    response = requests.get(FILLS_URL, auth=auth, params=fills_params)
    if response.status_code == 200:
        return response.json()
    else:
        logging.warning("fills api returned: " + str(response.status_code) + str(response.content))
        return list()


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_fills(side):
    fills_params = {
        'product_id': PRODUCT_ID}
    response = requests.get(FILLS_URL, auth=auth, params=fills_params)
    if response.status_code == 200:
        fills = response.json()
        return list([item for item in fills if item['side'] == side])
    else:
        logging.warning("fills api returned: " + str(response.status_code) + str(response.content))
        return list()


def get_sell_orders():
    sell_orders = []
    for open_order1 in get_open_orders():
        if open_order1['side'] == 'sell':
            sell_orders.append(open_order1)
    return sell_orders


def get_buy_orders():
    buy_orders = []
    for open_order2 in get_open_orders():
        if open_order2['side'] == 'buy':
            buy_orders.append(open_order2)
    return buy_orders


def get_num_sell_orders():
    return len(get_sell_orders())


def decrease_price_by_percentage(percentage, coin_price):
    float_price = float(coin_price)
    subtract_amount = float_price * percentage
    return float_price - subtract_amount


def increase_price_by_percentage(percentage, coin_price):
    float_price = float(coin_price)
    add_amount = float_price * percentage
    return float_price + add_amount


def decrease_price_by_amount(amount, coin_price):
    return float(coin_price) - amount


def increase_price_by_amount(amount, coin_price):
    return float(coin_price) + amount


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def place_order(order_type, price, size_to_trade):
    rounded_price = round(price, 2)

    order_params = {
        'type': 'limit',
        'side': order_type,
        'product_id': PRODUCT_ID,
        'price': rounded_price,
        'size': str(size_to_trade)}

    if 'buy' == order_type:
        cancel_after_times = [CANCEL_AFTER_DAY_VALUE, CANCEL_AFTER_HOUR_VALUE]
        order_params['time_in_force'] = 'GTT'
        order_params['cancel_after'] = random.choice(cancel_after_times)

    response = requests.post(ORDERS_URL, auth=auth, json=order_params)
    logging.info("\n\nOrder response" + str(response.status_code) + "." + str(response.content))

    response_json = response.json()
    if 'id' in response_json:
        return str(response.json()['id'])
    else:
        return None


def get_order_ids_from_fills(fills_list):
    return str(fills_list['order_id'])


def get_order_ids_from_orders(orders_list):
    return str(orders_list['id'])


def is_buy_order_id_in_fills(order_id, fills_list):
    ids = list(map(get_order_ids_from_fills, fills_list))
    return order_id.lower() in ids


def is_buy_order_id_in_orders(order_id, orders_list):
    ids = list(map(get_order_ids_from_orders, orders_list))
    return order_id.lower() in ids


def is_buy_order_filled(order_id):
    return is_buy_order_id_in_fills(order_id, get_fills())


def is_order_still_active(order_id):
    return is_buy_order_id_in_orders(order_id, get_open_orders())


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_available_balance():
    response = requests.get(ACCOUNTS_API_URL + USD_ACCOUNT_ID, auth=auth)

    if response.status_code == 200:
        json = response.json()
        return float(json['available'])
    else:
        logging.warning("available balance api returned: " + str(response.status_code) + str(response.content))
        return 0.00


@retryer(1000, 5)
@sleep_and_retry
@limits(calls=5, period=ONE_SECOND)
def get_account_ids():
    account_ids = dict()
    try:
        response = requests.get(ACCOUNTS_API_URL, auth=auth)
    except requests.exceptions.RequestException as e:
        logging.error("Requests exception occurred: " + str(e))
        response = requests.Response()
        response.code = 000

    if response.status_code == 200:
        json = response.json()
        for account in json:
            account_ids[str(account['currency'])] = str(account['id'])
        return account_ids
    else:
        logging.warning("accounts ids api returned:", str(response.status_code), str(response.content), sep=" ")
        return account_ids


# Copyright 2018, Justin B. Lovell, All rights reserved.
logging.basicConfig(filename='RyanOutput.log', level=logging.INFO)
placed_buy_orders = dict()
accounts = get_account_ids()
logging.info(accounts)
COIN_ACCOUNT_ID = accounts[CURRENCY]
USD_ACCOUNT_ID = accounts[USD_KEY]

get_buy_orders()
for order in get_buy_orders():
    if order['side'] == 'buy':
        placed_buy_orders[order['id']] = [order['price'], order['size']]

while True:
    current_market_price = None
    price_to_buy = None
    price_to_sell = None
    amount_to_buy = None
    amount_to_sell = None
    order_fill = None
    bought_price = None
    placed_buy_order_id = None
    placed_sell_order_id = None
    bought_amount = None
    amount_to_decrease_price = None

    while get_available_balance() > TRADE_DOLLAR_AMOUNT:
        current_market_price = get_current_price()

        amount_to_decrease_price = random.randint(MINIMUM_DECREASE_AMOUNT, MAXIMUM_DECREASE_AMOUNT)
        price_to_buy = decrease_price_by_amount(amount_to_decrease_price, current_market_price)
        amount_to_buy = round(TRADE_DOLLAR_AMOUNT / price_to_buy, 3)

        if amount_to_buy >= 0.001 and get_available_balance() > (price_to_buy * amount_to_buy):
            placed_buy_order_id = place_order('buy', price_to_buy, amount_to_buy)
            if placed_buy_order_id is not None:
                logging.info("\n\nPlaced a buy order for " + str(price_to_buy) + " at: " + str(datetime.datetime.now()))
                placed_buy_orders[placed_buy_order_id] = [price_to_buy, amount_to_buy]

    for order in list(placed_buy_orders):
        order_fill = get_fill(order)
        if order_fill:
            bought_price = float(order_fill[0]['price'])
            bought_amount = float(order_fill[0]['size'])
            price_to_sell = increase_price_by_amount(INCREASE_AMOUNT, bought_price)
            if float(get_current_price()) < price_to_sell:
                placed_sell_order_id = place_order('sell', price_to_sell, bought_amount)
            else:
                price_to_sell = increase_price_by_amount(INCREASE_AMOUNT, get_current_price())
                placed_sell_order_id = place_order('sell', price_to_sell, bought_amount)
                logging.info("\n\nIn order to avoid fees the buy amount of: "
                             + str(bought_price) + " was increased to: " + str(price_to_sell))
            if placed_sell_order_id is not None:
                logging.info("\n\nPlaced a sell order for " + str(price_to_sell)
                             + " at: " + str(datetime.datetime.now()))
                del placed_buy_orders[order]
