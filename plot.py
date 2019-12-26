import glob
import json
import os
from datetime import datetime, timedelta
from time import strftime, localtime

import pygal
import requests

from alapok import alapok


def str_to_datetime(unixtimestamp):
    return datetime.utcfromtimestamp(unixtimestamp)


def datestr_to_unixtimestamp(timestamp):
    return datetime.strptime(timestamp, "%Y.%m.%d").timestamp()


def unixtimestamp_to_str(unixtime):
    return unixtime.strftime('%Y.%m.%d')


def n_days_ago_unix_timestamp(days):
    _return = datetime.now() - timedelta(days=days)
    return _return.timestamp()


def calculate_days_difference(unixtimestamp):
    _return = datetime.now().timestamp() - unixtimestamp
    return int(_return / 86400)


def clean():
    filelist = glob.glob('./*.svg')
    for file in filelist:
        os.remove(file)


class MutualFund(object):
    def __init__(self, fund, days=90):
        self.base_url = 'https://api.bankmonitor.hu/api/public/mutual-fund/api-for-bankmonitor-hu/v4/mutual-funds/' \
                        'exchange-rates/HUF/'
        self.fund_name = fund.get('nev')
        self.fund_isin = fund.get('isin')
        self.fund_purchases = fund.get('vetel')
        self.fund_history = dict()
        self.purchase_history = dict()
        self.oldest_date = n_days_ago_unix_timestamp(max(days, 60))
        self.latest_rate = None

    def get_history(self):
        """
                :return: list example: [[1444255200000,1.077956],[1444341600000,1.079422],... ]
        """
        base_url = "https://www.kh.hu/megtakaritas-befektetes/hozamszamlalo-befektetesi-alap?" \
                   "p_p_id=yieldcalculator_WAR_yieldcalculatorportlet&p_p_lifecycle=2&p_p_state=normal&" \
                   "p_p_mode=view&p_p_resource_id=cmdGetChartData"
        data = {"yieldcalculator_WAR_yieldcalculatorportlet_dateFrom": int(self.oldest_date) * 1000,
                "_yieldcalculator_WAR_yieldcalculatorportlet_dateTo": datetime.utcnow().timestamp() * 1000,
                "_yieldcalculator_WAR_yieldcalculatorportlet_investments": self.fund_isin,
                "ajax": 0
                }
        _req = requests.post(base_url, data=data)
        if _req.status_code != 200:
            print('Error occurred: {}{}: {}, Size:'.format(self.base_url, self.fund_isin, _req, len(_req.text)))
        _tmp = json.loads(_req.text)
        resp = list()
        fund_index = 0
        for index in range(len(_tmp['diagram']['series'])):
            if _tmp['diagram']['series'][index].get('text').startswith('K&H'):
                fund_index = index
                print("Using {} data series".format(_tmp['diagram']['series'][index].get('text')))
                break
        count = 0
        for timestamp in _tmp['diagram']['scale-x']['labels']:
            resp.append([int(datestr_to_unixtimestamp(timestamp)) * 1000,
                         _tmp['diagram']['series'][fund_index]['values'][count]])
            count += 1
        return resp

    def process_history(self):
        _history = self.get_history()
        self.latest_rate = _history[-1][1]

        for item in _history:
            timestamp_no_mseconfs = item[0] / 1000
            if timestamp_no_mseconfs > self.oldest_date:
                day_string = unixtimestamp_to_str(str_to_datetime(timestamp_no_mseconfs))
                self.fund_history[day_string] = item[1]

    def calculate_gain_percent(self, rate_at_buy):
        _return = 0
        if rate_at_buy:
            _return = round(float(self.latest_rate) / float(rate_at_buy) * 100, 2)
        return _return

    def add_purchase_history_to_fund_history(self):
        for day in self.fund_purchases:
            if day not in self.fund_history.keys():
                self.fund_history[day] = None

    def process_data(self):
        """
        Sample purchase_history item:
        {
            "rate" = 1.076387,
            "day_string" = "2018.05.14",
            "purchase_rate" = 1.076387, # or None
            "purchase_gain_percent" = 4.5 # or None
        }
        """
        self.process_history()
        self.add_purchase_history_to_fund_history()
        _prev_rate = None
        for day in sorted(self.fund_history.keys()):
            rate = self.fund_history[day]
            purchase_gain_percent = None
            purchase_rate = None
            if day in self.fund_purchases:
                if rate:
                    _prev_rate = rate
                purchase_rate = _prev_rate
                purchase_gain_percent = self.calculate_gain_percent(_prev_rate)
            history_item = {
                "rate": rate,
                "purchase_rate": purchase_rate,
                "purchase_gain_percent": purchase_gain_percent
            }
            self.purchase_history[day] = history_item
            _prev_rate = rate

    def render_chart(self):
        _purchases = list()
        _history = list()
        _x_legends = sorted(self.purchase_history.keys())
        _max_gain = 0
        for day in sorted(self.purchase_history.keys()):
            _purchase_gain_percent = self.purchase_history[day].get('purchase_gain_percent')
            _history.append(self.purchase_history[day].get('rate'))
            _purchases.append({
                'value': self.purchase_history[day].get('purchase_rate'),
                'label': '{}%'.format(_purchase_gain_percent)
            })
            if _purchase_gain_percent and _purchase_gain_percent > _max_gain:
                _max_gain = _purchase_gain_percent
        line_chart = pygal.Line(print_values=False, show_legend=False)
        line_chart.config.x_label_rotation = 45
        line_chart.x_labels_major = _x_legends[::7]
        line_chart.config.x_title = "Dátum"
        line_chart.config.y_title = "Legnagyob hozam: {}%".format(_max_gain)
        line_chart.config.width = 1680
        line_chart.show_minor_x_labels = False
        line_chart.title = '{} árfolyam'.format(self.fund_name)
        line_chart.x_labels = map(str, _x_legends)
        line_chart.add('Árfolyam', _history)
        line_chart.add('Vétel', _purchases, allow_interruptions=True, print_values=True, dots_size=5)
        line_chart.render_to_file('{}.svg'.format(self.fund_name))

    @staticmethod
    def save_html():
        html_head = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 ' \
                    'Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd"> \
                    <html xmlns="http://www.w3.org/1999/xhtml"> \
                    <head>' \
                    '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />' \
                    '<title>{}</title>' \
                    '</head>' \
                    '<body>'.format(strftime(" %Y %b %d %H:%M:%S", localtime()))
        html_bottom = '</body></html>'
        filelist = glob.glob('./*.svg')
        with open('index.html', 'w') as f:
            f.write(html_head)
            for file in sorted(filelist):
                f.write(
                    '<object id="E" type="image/svg+xml" data="{0}" ><param name="src" value="{0}"></object>'.format(
                        file))
            f.write(html_bottom)


if __name__ == '__main__':
    clean()
    for alap in alapok:
        oldest_purchase = int(datetime.now().timestamp())
        for puchase in alap.get('vetel'):
            transformed_putchase = int(datestr_to_unixtimestamp(puchase))
            if transformed_putchase < oldest_purchase:
                oldest_purchase = transformed_putchase
        prog = MutualFund(alap, calculate_days_difference(oldest_purchase) + 2)
        prog.process_data()
        prog.render_chart()
        prog.save_html()
