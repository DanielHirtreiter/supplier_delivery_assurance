"""Small Monte Carlo helpers. IID, equally weighted scenario rows only.

NumPy >= 1.22; SciPy >= 1.7. No business defaults or global RNG state.
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def _integer(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return int(value)


def _probability(value, name, strict=False):
    if not np.isfinite(value) or not (0 < value < 1 if strict else 0 <= value <= 1):
        raise ValueError(f'{name} must be finite and within ' + ('(0,1)' if strict else '[0,1]'))
    return float(value)


def _sample(x, minimum=1):
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or len(x) < minimum or not np.all(np.isfinite(x)):
        raise ValueError(f'Expected a finite 1-D sample with at least {minimum} values')
    return x


def lognormal_from_moments(mean, sd):
    """Frozen SciPy RV from positive original-unit arithmetic mean and SD."""
    if not np.all(np.isfinite([mean, sd])) or mean <= 0 or sd <= 0:
        raise ValueError('mean and sd must be finite and positive; assign constants directly')
    sigma2 = np.log1p((sd / mean) ** 2)
    return stats.lognorm(s=np.sqrt(sigma2), scale=np.exp(np.log(mean) - sigma2 / 2))


def pert(low, mode, high, weight=4.0):
    """Frozen scaled Beta-PERT. weight=4 is a modelling convention."""
    if not np.all(np.isfinite([low, mode, high, weight])) or not low <= mode <= high or low >= high or weight < 0:
        raise ValueError('Require low <= mode <= high, low < high, and nonnegative weight')
    width = high - low
    a = 1 + weight * (mode - low) / width
    b = 1 + weight * (high - mode) / width
    return stats.beta(a, b, loc=low, scale=width)


def correlation_factor(correlation, tolerance=1e-10):
    """Return A such that A @ A.T = R, allowing singular PSD matrices.

    Only roundoff eigenvalues within tolerance are clipped; no material repair.
    """
    r = np.asarray(correlation, dtype=float)
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('tolerance must be positive')
    if r.ndim != 2 or r.shape[0] == 0 or r.shape[0] != r.shape[1] or not np.all(np.isfinite(r)):
        raise ValueError('Correlation must be a finite nonempty square matrix')
    if not np.allclose(r, r.T, atol=tolerance, rtol=0) or not np.allclose(np.diag(r), 1, atol=tolerance, rtol=0):
        raise ValueError('Correlation must be symmetric with unit diagonal')
    if np.any(np.abs(r) > 1 + tolerance):
        raise ValueError('Correlation entries exceed [-1,1]')
    eigenvalues, eigenvectors = np.linalg.eigh((r + r.T) / 2)
    if eigenvalues.min() < -tolerance:
        raise ValueError(f'Correlation is not PSD: minimum eigenvalue {eigenvalues.min():.6g}')
    return eigenvectors * np.sqrt(np.maximum(eigenvalues, 0))


def sample_marginals(marginals, n, rng, correlation=None, df=None):
    """Draw columns from SciPy frozen marginals via independence or a copula.

    correlation is LATENT dependence, not a target output Pearson matrix.
    df=None selects Gaussian; finite df>0 selects t copula with explicit R.
    Each row is an independent scenario. Deterministic drivers belong in model.
    """
    n = _integer(n, 'n')
    d = len(marginals)
    if d == 0:
        raise ValueError('Supply at least one marginal')
    if df is not None and (not np.isfinite(df) or df <= 0 or correlation is None):
        raise ValueError('t copula requires df>0 and an explicit latent correlation matrix')
    if correlation is None:
        uniforms = rng.random((n, d))
    else:
        factor = correlation_factor(correlation)
        if factor.shape != (d, d):
            raise ValueError('Correlation dimension does not match marginals')
        latent = rng.standard_normal((n, d)) @ factor.T
        if df is None:
            uniforms = stats.norm.cdf(latent)
        else:
            latent /= np.sqrt(rng.chisquare(df, n) / df)[:, None]
            uniforms = stats.t.cdf(latent, df)
    # Prevent inverse-CDF infinities from floating-point endpoints only.
    uniforms = np.clip(uniforms, np.finfo(float).eps, 1 - np.finfo(float).eps)
    draws = np.column_stack([rv.ppf(uniforms[:, j]) for j, rv in enumerate(marginals)])
    if draws.shape != (n, d) or not np.all(np.isfinite(draws)):
        raise ValueError('Marginal transform returned invalid or nonfinite values')
    return draws


def compound_poisson(rate, severity, n, rng, max_events=5_000_000):
    """Independent nonnegative IID severities and Poisson event count.

    Raise on excess allocation; chunk explicitly instead of truncating losses.
    """
    n = _integer(n, 'n')
    max_events = _integer(max_events, 'max_events')
    if not np.isfinite(rate) or rate < 0:
        raise ValueError('rate must be finite and nonnegative')
    counts = rng.poisson(rate, n)
    total = int(counts.sum())
    if total > max_events:
        raise MemoryError('Too many events for this batch; reduce n or increase the explicit budget')
    if total == 0:
        return np.zeros(n)
    sizes = np.asarray(severity.rvs(size=total, random_state=rng), dtype=float)
    if sizes.shape != (total,) or not np.all(np.isfinite(sizes)) or np.any(sizes < 0):
        raise ValueError('Severity must produce finite nonnegative values')
    return np.bincount(np.repeat(np.arange(n), counts), weights=sizes, minlength=n)


def empirical_var_es(losses, alpha=0.95):
    """Inverse empirical CDF VaR and exact empirical tail integral ES.

    Handles atoms/ties and fractional tail mass. Negative losses are allowed.
    """
    x = _sample(losses)
    alpha = _probability(alpha, 'alpha', strict=True)
    var = float(np.quantile(x, alpha, method='inverted_cdf'))
    es = var + float(np.maximum(x - var, 0).mean()) / (1 - alpha)
    return {'alpha': alpha, 'var': var, 'es': es}


def mean_interval(values, confidence=0.95):
    """Student-t interval for MC mean: approximate for non-normal finite-variance rows."""
    x = _sample(values, minimum=2)
    confidence = _probability(confidence, 'confidence', strict=True)
    mean = float(x.mean())
    se = float(x.std(ddof=1) / np.sqrt(len(x)))
    half = float(stats.t.ppf((1 + confidence) / 2, len(x) - 1) * se)
    return {'mean': mean, 'mc_se': se, 'confidence': confidence, 'ci': [mean - half, mean + half]}


def event_interval(events, confidence=0.95):
    """Two-sided exact binomial interval for IID scenario event indicators."""
    events = np.asarray(events)
    confidence = _probability(confidence, 'confidence', strict=True)
    if events.ndim != 1 or events.size == 0 or not np.all((events == 0) | (events == 1)):
        raise ValueError('events must be a nonempty 1-D array of booleans or 0/1')
    k, n = int(events.sum()), len(events)
    ci = stats.binomtest(k, n).proportion_ci(confidence_level=confidence, method='exact')
    return {'count': k, 'n': n, 'probability': k / n, 'confidence': confidence, 'ci': [float(ci.low), float(ci.high)]}


def loss_summary(losses, alpha=0.95, threshold=0.0, confidence=0.95):
    """IID loss summary; threshold event is strictly L > threshold."""
    x = _sample(losses, minimum=2)
    if not np.isfinite(threshold):
        raise ValueError('threshold must be finite')
    result = {'n': len(x), 'mean': mean_interval(x, confidence), 'sd': float(x.std(ddof=1)),
              'quantiles': dict(zip(['p05', 'p50', 'p95'], map(float, np.quantile(x, [.05, .5, .95], method='inverted_cdf')))),
              **empirical_var_es(x, alpha), 'threshold': float(threshold),
              'exceedance': event_interval(x > threshold, confidence),
              'nominal_tail_observations': len(x) * (1 - alpha)}
    result['warnings'] = []
    if result['nominal_tail_observations'] < 100:
        result['warnings'].append('Sparse nominal tail: assess tail precision explicitly; 100 is only a heuristic.')
    if result['exceedance']['count'] == 0:
        result['warnings'].append('No exceedance observed; inspect the nonzero probability upper bound.')
    return result


def bootstrap_tail_intervals(losses, rng, alpha=0.95, resamples=300, confidence=0.95):
    """IID percentile bootstrap diagnostics, not reliable for sparse/irregular tails.

    Uses one resample at a time to bound memory. No seed reset or global RNG.
    """
    x = _sample(losses, minimum=2)
    alpha = _probability(alpha, 'alpha', strict=True)
    confidence = _probability(confidence, 'confidence', strict=True)
    resamples = _integer(resamples, 'resamples', minimum=2)
    estimates = np.empty((resamples, 2))
    for i in range(resamples):
        r = empirical_var_es(x[rng.integers(0, len(x), len(x))], alpha)
        estimates[i] = [r['var'], r['es']]
    q = [(1 - confidence) / 2, (1 + confidence) / 2]
    bounds = np.quantile(estimates, q, axis=0)
    warnings = []
    if len(x) * (1 - alpha) < 100:
        warnings.append('Sparse tail; bootstrap intervals may understate uncertainty.')
    if np.any(bounds[0] == bounds[1]):
        warnings.append('A collapsed interval is not proof of precise tails; inspect atoms and missing mechanisms.')
    return {'method': 'IID percentile bootstrap diagnostic', 'confidence': confidence,
            'resamples': resamples, 'var_ci': bounds[:, 0].tolist(), 'es_ci': bounds[:, 1].tolist(), 'warnings': warnings}
