"""Same-window 29-, 23-, and 6-stock tangency sensitivity using accepted inputs."""
from pathlib import Path
from datetime import datetime, timezone
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/stage1/universe_sensitivity'

def estimate(frame, rf):
    values = frame.to_numpy()
    mean = values.mean(axis=0)
    excess_mean = mean - rf.mean()
    covariance = np.cov(values, rowvar=False, ddof=1)
    eigenvalues = np.linalg.eigvalsh(covariance)
    assert eigenvalues.min() > 0
    direction = np.linalg.solve(covariance, excess_mean)
    assert direction.sum() > 0
    weights = direction / direction.sum()
    assert abs(weights.sum()-1) < 1e-12
    assert np.max(np.abs(covariance @ direction - excess_mean)) < 1e-12
    series = values @ weights
    volatility = series.std(ddof=1) * np.sqrt(12)
    stats = {
        'annual_mean': float(series.mean()*12),
        'annual_volatility': float(volatility),
        'model_sharpe_annual': float((series-rf).mean()*12/volatility),
        'gross_exposure': float(np.abs(weights).sum()),
        'short_exposure': float(-weights[weights<0].sum()),
    }
    assert abs(stats['model_sharpe_annual']-np.sqrt(12*excess_mean @ direction)) < 1e-10
    return {
        'tickers': frame.columns.tolist(),
        'weights': weights.tolist(),
        'mean_monthly': mean.tolist(),
        'mean_rf_monthly': float(rf.mean()),
        'covariance_monthly': covariance.tolist(),
        'smallest_eigenvalue': float(eigenvalues.min()),
        'normalization_denominator': float(direction.sum()),
        **stats,
    }, series

def main():
    config = json.loads((ROOT/'config/universe.json').read_text(encoding='utf-8'))
    returns = pd.read_csv(ROOT/'data/processed/returns_us_monthly.csv',index_col=0,float_precision='round_trip')
    factors = pd.read_csv(ROOT/'data/processed/ff3_monthly.csv',index_col=0,float_precision='round_trip')
    accepted = json.loads((ROOT/'results/stage1/results.json').read_text(encoding='utf-8'))
    tickers = config['primary_universe']['tickers']
    assert returns.columns.tolist() == tickers and returns.shape == (130,29)
    assert returns.index.tolist() == factors.index.tolist()
    assert returns.index[0] == '2015-11' and returns.index[-1] == '2026-08'
    assert returns.index.is_unique and np.isfinite(returns.to_numpy()).all()
    cutoff = '2026-08-31'
    removed = {
        m['quote_symbol'] for m in config['primary_universe']['members']
        if m['included'] and m.get('later_index_removal_date') and m['later_index_removal_date'] <= cutoff
    }
    assert removed == {'GE','XOM','PFE','RTX','INTC','VZ'}
    retained = [ticker for ticker in tickers if ticker not in removed]
    removed_order = [ticker for ticker in tickers if ticker in removed]
    assert len(retained) == 23
    rf = factors['RF'].to_numpy()
    model29, series29 = estimate(returns,rf)
    model23, series23 = estimate(returns[retained],rf)
    model6, series6 = estimate(returns[removed_order],rf)
    assert np.allclose(model29['weights'],accepted['models']['full_sample']['weights'],rtol=0,atol=2e-14)
    assert model29['model_sharpe_annual'] + 1e-10 >= model23['model_sharpe_annual']
    assert model29['model_sharpe_annual'] + 1e-10 >= model6['model_sharpe_annual']
    assert not set(retained).intersection(removed_order)
    weight29 = pd.Series(model29['weights'],index=tickers)
    weight23 = pd.Series(model23['weights'],index=retained)
    change = weight23 - weight29.loc[retained]
    sensitivity = {
        'common_stock_weight_correlation': float(np.corrcoef(weight29.loc[retained],weight23)[0,1]),
        'common_stock_sign_changes': int(((weight29.loc[retained]*weight23)<0).sum()),
        'sign_change_tickers': [ticker for ticker in retained if weight29[ticker]*weight23[ticker]<0],
        'largest_change_ticker': str(change.abs().idxmax()),
        'largest_signed_weight_change': float(change.loc[change.abs().idxmax()]),
        'model_sharpe_change_23_minus_29': model23['model_sharpe_annual']-model29['model_sharpe_annual'],
        'model_sharpe_difference_23_minus_6': model23['model_sharpe_annual']-model6['model_sharpe_annual'],
    }
    result = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'analysis_version': 'dow2015_29_universe_sensitivity',
        'sample': {'start':'2015-11','end':'2026-08','months':130},
        'removed_tickers': [ticker for ticker in tickers if ticker in removed],
        'models': {'all_29':model29,'retained_23':model23,'later_removals_6':model6},
        'sensitivity': sensitivity,
        'methods': {
            'universe_selection':'Retained 23 and six disclosed later DJIA removals partition the same historical cohort, using status through the sample end; all 29 remain primary.',
            'covariance':'Raw monthly return sample covariance, ddof=1; direct solve without shrinkage or clipping.',
            'weights':'Unrestricted, normalized to sum to one; re-estimated separately over the same 130 months.',
            'sharpe':'Annualized mean excess return / annualized raw-return volatility.',
            'evaluation':'Same-window fitted performance, monthly target-weight rebalancing.',
            'precision':'Float64 calculations; displayed numbers rounded to three decimals.',
        },
        'limits': [
            'This changes the eligible universe, rather than randomly resampling observations.',
            'Later-membership selection uses information unavailable at the 2015 start; the 23-stock group is an ex-post comparison.',
            'These six stocks left the DJIA; index removal does not itself mean bankruptcy or exchange delisting.',
            'The 29-stock unrestricted feasible set includes both subset feasible sets via zero weights, so its fitted maximum Sharpe cannot be lower.',
            'The disjoint 23- and 6-stock portfolios have different investment opportunities; fitted Sharpe differences reflect composition, covariance and optimization, not a causal effect of index removal.',
            'The difference does not identify or quantify market-wide survivorship bias or future performance.',
            'The primary 29-stock cohort and its accepted results are unchanged.',
        ],
        'source_files': ['config/universe.json','data/processed/returns_us_monthly.csv','data/processed/ff3_monthly.csv','results/stage1/results.json'],
    }
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    stats = pd.DataFrame([
        {'portfolio':'All 29 tangency','assets':29,**{k:model29[k] for k in ('annual_mean','annual_volatility','model_sharpe_annual','gross_exposure')}},
        {'portfolio':'Retained 23 tangency','assets':23,**{k:model23[k] for k in ('annual_mean','annual_volatility','model_sharpe_annual','gross_exposure')}},
        {'portfolio':'Later-removal 6 tangency','assets':6,**{k:model6[k] for k in ('annual_mean','annual_volatility','model_sharpe_annual','gross_exposure')}},
    ])
    stats.to_csv(OUT/'portfolio_statistics.csv',index=False,float_format='%.17g')
    weights = pd.DataFrame({'ticker':tickers,'included_in_23':[t not in removed for t in tickers],
                           'weight_29':weight29.to_numpy(),'weight_23':weight23.reindex(tickers).to_numpy(),
                           'weight_6':pd.Series(model6['weights'],index=removed_order).reindex(tickers).to_numpy()})
    weights.to_csv(OUT/'weights.csv',index=False,float_format='%.17g',na_rep='')
    pd.DataFrame({'All 29 tangency':series29,'Retained 23 tangency':series23,'Later-removal 6 tangency':series6},index=returns.index).to_csv(OUT/'portfolio_monthly_returns.csv',float_format='%.17g')
    print(json.dumps({'statistics':stats.to_dict(orient='records'),'sensitivity':sensitivity,'output':str(OUT)},ensure_ascii=False))

if __name__ == '__main__':
    main()
