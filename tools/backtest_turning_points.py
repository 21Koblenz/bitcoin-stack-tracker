#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, importlib.util
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'custom_components' / 'bitcoin_stack_tracker' / 'buy_opportunity.py'
spec = importlib.util.spec_from_file_location('bst_buy_opportunity', MODULE)
mod = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(mod)

EVENTS = [
    ('bottom','2013-07-05','2013 first-cycle crash low'),
    ('top','2013-12-04','2013 second blow-off top'),
    ('bottom','2015-01-14','2014/15 bear-market low'),
    ('top','2017-12-17','2017 cycle top'),
    ('bottom','2018-12-15','2018 bear-market low'),
    ('top','2019-06-26','2019 recovery local top'),
    ('bottom','2020-03-13','2020 COVID crash'),
    ('top','2021-04-14','2021 first major top'),
    ('bottom','2021-07-20','2021 summer low'),
    ('top','2021-11-10','2021 second major top'),
    ('bottom','2022-06-18','2022 deleveraging low'),
    ('bottom','2022-11-21','2022 FTX-region low'),
    ('top','2024-03-14','2024 first ATH-region top'),
    ('bottom','2024-08-05','2024 correction low'),
    ('top','2025-10-06','2025 ATH-region top'),
    ('bottom','2026-02-05','2026 bear-market stress low'),
]


def load_prices(path: Path) -> dict[str,float]:
    prices={}
    with path.open(newline='',encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try: price=float(row.get('PriceUSD') or '')
            except ValueError: continue
            day=str(row.get('time') or '')[:10]
            if price>0 and day: prices[day]=price
    return prices


def result_for(prices: dict[str,float], day: str):
    if day not in prices: return None
    # calculate_buy_opportunity itself filters future data, but passing the prefix
    # here makes the causal property explicit and independently auditable.
    prefix={k:v for k,v in prices.items() if k<=day}
    return mod.calculate_buy_opportunity(prefix,prices[day],currency='USD',as_of_day=day)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('csv',type=Path)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    prices=load_prices(args.csv)
    rows=[]
    for kind, day_s, label in EVENTS:
        if day_s not in prices: continue
        base=result_for(prices,day_s); tp=base['turning_points']
        d=date.fromisoformat(day_s)
        best_confirm=(-1.0,None,None)
        first_cross=None
        threshold=float(tp['thresholds']['confirmation'])
        for offset in (0, 3, 7, 14, 21, 30):
            x=(d+timedelta(days=offset)).isoformat()
            if x not in prices: continue
            r=result_for(prices,x); t=r['turning_points']
            value=float(t['bottom_confirmation'] if kind=='bottom' else t['top_confirmation'])
            if value>best_confirm[0]: best_confirm=(value,x,t['market_phase'])
            zone_mem=float(t['bottom_zone_memory'] if kind=='bottom' else t['top_zone_memory'])
            if first_cross is None and value>=threshold and zone_mem>=float(t['thresholds']['zone']):
                first_cross=(x,offset,value,zone_mem,t['market_phase'])
        rows.append({
            'kind':kind,'event_day':day_s,'label':label,'price':prices[day_s],
            'main_score':base['score'],'bottom_zone':tp['bottom_zone'],'bottom_confirmation':tp['bottom_confirmation'],
            'top_zone':tp['top_zone'],'top_confirmation':tp['top_confirmation'],'phase':tp['market_phase'],
            'best_confirmation_30d':best_confirm[0],'best_confirmation_day':best_confirm[1],
            'first_confirm_day':first_cross[0] if first_cross else None,
            'first_confirm_lag_days':first_cross[1] if first_cross else None,
            'first_confirm_score':first_cross[2] if first_cross else None,
            'first_confirm_zone_memory':first_cross[3] if first_cross else None,
            'first_confirm_phase':first_cross[4] if first_cross else None,
        })
    if args.out:
        with args.out.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    for r in rows:
        print(r)

if __name__=='__main__': main()
