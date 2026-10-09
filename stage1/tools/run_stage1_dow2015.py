"""Offline Stage 1 calculation for the authorized 2015 Dow cohort.

Run after prepare_dow2015_inputs.py; no network or machine-specific lake access.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from portfolio_math import estimate, long_only_tangency, portfolio_stats

ROOT = Path(__file__).resolve().parents[1]

def compute(processed: Path, config: dict):
    read = lambda name: pd.read_csv(processed / name, index_col=0, float_precision='round_trip')
    returns, factors = read('returns_us_monthly.csv'), read('ff3_monthly.csv')
    caps = pd.read_csv(processed / 'value_weights.csv', float_precision='round_trip').set_index('ticker')
    tickers = config['primary_universe']['tickers']
    start, end = config['sample']['return_start_month'], config['sample']['return_end_month']
    months = pd.period_range(start, end, freq='M').astype(str).tolist()
    assert returns.columns.tolist() == tickers and returns.index.tolist() == months
    assert returns.shape == (len(months), len(tickers)) and len(months) >= 96
    assert factors.index.tolist() == months and caps.index.tolist() == tickers
    assert set(caps.as_of_date) == {config['sample']['value_weight_as_of_date']}
    assert set(caps.currency) == {'USD'}
    rf, value = factors.RF, caps.value_weight
    assert np.isfinite(returns.to_numpy()).all() and np.isfinite(factors.to_numpy()).all()
    assert value.gt(0).all() and abs(value.sum()-1) < 1e-14
    half = len(returns)//2
    windows = {'full_sample': returns, 'first_half': returns.iloc[:half], 'second_half': returns.iloc[half:]}
    models = {name: estimate(frame, rf) for name, frame in windows.items()}
    constrained = long_only_tangency(models['full_sample'])
    full, first, second = [models[k] for k in windows]
    weights = pd.DataFrame({'ticker': tickers, 'tangency_weight': full['weights'],
                           'value_weight': value.to_numpy(), 'long_only_weight': constrained['weights']})
    drift = pd.DataFrame({'ticker': tickers, 'full_sample_weight': full['weights'],
                         'first_half_weight': first['weights'], 'second_half_weight': second['weights']})
    a, b = np.asarray(first['weights']), np.asarray(second['weights'])
    delta = b-a
    stability = {'first_second_weight_correlation': float(np.corrcoef(a,b)[0,1]),
        'first_second_l1_weight_distance': float(abs(delta).sum()),
        'sign_changes': int(((a*b)<0).sum()),
        'largest_change_ticker': tickers[int(abs(delta).argmax())],
        'largest_absolute_weight_change': float(abs(delta).max()),
        'first_half_weight_at_largest_change': float(a[int(abs(delta).argmax())]),
        'second_half_weight_at_largest_change': float(b[int(abs(delta).argmax())])}
    value_name = f"Value weighted ({config['sample']['value_weight_as_of_date']})"
    portfolios = {'Tangency (full sample)': np.asarray(full['weights']), value_name: value.to_numpy(),
        'Long-only tangency (full sample)': np.asarray(constrained['weights']),
        'Tangency (first half)': a, 'Tangency (second half)': b}
    stats = pd.DataFrame([portfolio_stats(frame, rf, w, name, window)
        for name,w in portfolios.items() for window,frame in windows.items()])
    excess = returns.sub(rf,axis=0)
    summary = pd.DataFrame({'ticker': tickers, 'observations': len(returns),
        'mean_monthly': returns.mean().to_numpy(), 'mean_annual': returns.mean().to_numpy()*12,
        'volatility_monthly': returns.std(ddof=1).to_numpy(),
        'volatility_annual': returns.std(ddof=1).to_numpy()*np.sqrt(12),
        'mean_excess_annual': excess.mean().to_numpy()*12,
        'min_month': returns.min().to_numpy(), 'max_month': returns.max().to_numpy(),
        'mean_standard_error_monthly': returns.std(ddof=1).to_numpy()/np.sqrt(len(returns))})
    covariance = pd.DataFrame(full['covariance_monthly'], index=tickers, columns=tickers)
    covariance.index.name = 'ticker'
    series = pd.DataFrame({name: returns.to_numpy()@w for name,w in portfolios.items()},index=returns.index)
    series.index.name = 'Month'
    means = pd.DataFrame({'ticker': tickers, 'mean_monthly': full['mean_monthly'],
                         'excess_mean_monthly': full['excess_mean_monthly']})
    result = {'schema_version': 2, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'numerical_analysis_completed_requires_validation', 'asset_count': len(tickers),
        'methods': {'sample_months': len(returns), 'return_start': start, 'return_end': end,
            'annualization_months':12, 'mean':'Arithmetic mean of monthly simple returns',
            'covariance':'Sample raw-return covariance, ddof=1',
            'risk_free':'Month-aligned official French RF; each window uses its own mean',
            'primary_sharpe':'sqrt(12)*mean(Rp-RF)/std(Rp,ddof=1)',
            'value_weights':f"Static {config['sample']['value_weight_as_of_date']} Yahoo company market-cap vector over the same 29 stocks",
            'subsamples': f"First {half} months and remaining {len(returns)-half}; independently estimated",
            'return_policy': config['data_policy']['return_policy'],
            'precision':'Float64 without intermediate rounding; displays to three decimals',
            'primary_cleaning':'No winsorization, trimming, ridge, pseudoinverse or clipping'},
        'models':models, 'long_only':constrained, 'stability':stability,
        'source_files':{'returns':'data/processed/returns_us_monthly.csv','factors':'data/processed/ff3_monthly.csv',
            'caps':'data/processed/value_weights.csv','validation':'validation/reproduction.json'},
        'limitations':config['limitations'] + [
            'Same-sample fitted Sharpe is not an independent performance estimate.',
            'Subsample movement can reflect estimation error and changing market parameters.',
            'Static sample-end capitalization weights are descriptive and contain future information for earlier months.',
            'Borrowing, stock-borrow availability, funding and trading costs are excluded.']}
    tables = {'exhibit_1a_summary_stats.csv':summary, 'exhibit_1b_weights.csv':weights,
        'exhibit_1c_subsample_weights.csv':drift,'portfolio_statistics.csv':stats,
        'portfolio_monthly_returns.csv':series,'estimated_mean_vectors.csv':means,
        'estimated_covariance_monthly.csv':covariance}
    return result,tables

def write_outputs(result,tables,out):
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items():
        index = name in {'portfolio_monthly_returns.csv','estimated_covariance_monthly.csv'}
        table.to_csv(out/name,index=index,float_format='%.17g')
        back = pd.read_csv(out/name,index_col=0 if index else None,float_precision='round_trip')
        cols = table.select_dtypes(include=[np.number]).columns
        assert np.array_equal(back[cols].to_numpy(),table[cols].to_numpy())
    (out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')

def plot_figures(tables,result,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter
    directory=out/'figures'; directory.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    def paired(frame,columns,labels,stem):
        n=len(frame); split=(n+1)//2
        fig,axes=plt.subplots(1,2,figsize=(9.8,4.9),sharex=True)
        arr=frame[columns].to_numpy(); low=min(0,float(arr.min())); high=max(0,float(arr.max())); span=high-low
        limits=(low-.06*span,high+.08*span)
        colors=['#243F59','#B8873B']
        for ax,sub in zip(axes,[frame.iloc[:split],frame.iloc[split:]]):
            y=np.arange(len(sub))
            for k,col in enumerate(columns):
                ax.barh(y+(k-.5)*.34,sub[col],height=.32,color=colors[k],label=labels[k])
            ax.set_yticks(y,sub.ticker); ax.invert_yaxis(); ax.set_xlim(limits)
            ax.axvline(0,color='#555555',lw=.7); ax.grid(axis='x',color='#dddddd',lw=.5)
            ax.set_axisbelow(True); ax.xaxis.set_major_formatter(PercentFormatter(1,decimals=0))
            ax.set_xlabel('Portfolio weight')
        handles,legend=axes[0].get_legend_handles_labels()
        fig.legend(handles,legend,loc='upper center',ncol=2,frameon=False)
        fig.tight_layout(rect=(0,0,1,.93))
        for ext in ['png','svg']: fig.savefig(directory/f'{stem}.{ext}',dpi=220,bbox_inches='tight')
        plt.close(fig)
    paired(tables['exhibit_1b_weights.csv'],['tangency_weight','value_weight'],
           ['Unrestricted tangency','Value weighted'],'exhibit_1b')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--processed',type=Path,default=ROOT/'data/processed')
    parser.add_argument('--config',type=Path,default=ROOT/'config/universe.json')
    parser.add_argument('--out',type=Path,default=ROOT/'results/stage1')
    args=parser.parse_args()
    config=json.loads(args.config.read_text(encoding='utf-8'))
    result,tables=compute(args.processed,config); write_outputs(result,tables,args.out); plot_figures(tables,result,args.out)
    print(json.dumps({'assets':result['asset_count'],'months':result['methods']['sample_months'],
        'model_sharpe':result['models']['full_sample']['model_sharpe_annual'],'output':str(args.out)}))

if __name__=='__main__': main()
