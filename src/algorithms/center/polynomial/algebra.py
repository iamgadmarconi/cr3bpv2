import numpy as np
from numba import cuda, get_num_threads, get_thread_id, njit, prange
from numba.typed import List

from algorithms.center.polynomial.base import (decode_multiindex,
                                               encode_multiindex,
                                               fill_exponents)
from algorithms.variables import N_VARS
from config import FASTMATH


@njit(fastmath=FASTMATH, cache=True)
def _poly_add(p: np.ndarray, q: np.ndarray, out: np.ndarray) -> None:
    """
    Add two polynomial coefficient arrays element-wise.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the first polynomial
    q : numpy.ndarray
        Coefficient array of the second polynomial
    out : numpy.ndarray
        Output array where the result will be stored
        
    Returns
    -------
    None
        The result is stored in the 'out' array
        
    Notes
    -----
    This function assumes 'p', 'q', and 'out' have the same shape.
    Performs element-wise addition without any validation checks.
    """
    for i in range(p.shape[0]):
        out[i] = p[i] + q[i]

@njit(fastmath=FASTMATH, cache=True)
def _poly_scale(p: np.ndarray, alpha, out: np.ndarray) -> None:
    """
    Scale a polynomial coefficient array by a constant factor.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial
    alpha : numeric
        Scaling factor (can be real or complex)
    out : numpy.ndarray
        Output array where the result will be stored
        
    Returns
    -------
    None
        The result is stored in the 'out' array
        
    Notes
    -----
    This function assumes 'p' and 'out' have the same shape.
    Performs element-wise multiplication without any validation checks.
    """
    for i in range(p.shape[0]):
        out[i] = alpha * p[i]

@njit(fastmath=FASTMATH, cache=False, parallel=True)
def _poly_mul(p: np.ndarray, deg_p: int, q: np.ndarray, deg_q: int, psi, clmo, encode_dict_list) -> np.ndarray:
    """
    Multiply two polynomials using their coefficient arrays.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the first polynomial
    deg_p : int
        Degree of the first polynomial
    q : numpy.ndarray
        Coefficient array of the second polynomial
    deg_q : int
        Degree of the second polynomial
    psi : numpy.ndarray
        Combinatorial table from init_index_tables
    clmo : numba.typed.List
        List of arrays containing packed multi-indices
    encode_dict_list : numba.typed.List
        List of dictionaries mapping packed multi-indices to their positions
        
    Returns
    -------
    numpy.ndarray
        Coefficient array of the product polynomial
        
    Notes
    -----
    This function implements parallel computation of polynomial multiplication
    using a thread-safe approach. Each thread accumulates partial results in
    a private array before a final reduction step combines them.
    
    The output polynomial will have degree deg_p + deg_q.
    """
    deg_r = deg_p + deg_q
    out_len = psi[N_VARS, deg_r]
    nT = get_num_threads()

    scratch = np.zeros((nT, out_len), dtype=p.dtype)   # private copies

    for i in prange(p.shape[0]):
        tid = get_thread_id()          # → row in scratch
        pi = p[i]
        if pi == 0:
            continue
        ki = decode_multiindex(i, deg_p, clmo)
        for j in range(q.shape[0]):
            qj = q[j]
            if qj == 0:
                continue
            kj = decode_multiindex(j, deg_q, clmo)
            # build sum of exponents explicitly to avoid potential nopython
            # pitfalls of `ki + kj` with newly allocated arrays
            ks = np.empty(N_VARS, dtype=np.int64)
            for m in range(N_VARS):
                ks[m] = ki[m] + kj[m]
            idx = encode_multiindex(ks, deg_r, encode_dict_list)
            if idx != -1:
                scratch[tid, idx] += pi * qj      # no race

    r = np.zeros(out_len, dtype=p.dtype)
    for tid in range(nT):
        r += scratch[tid]

    return r

@njit(fastmath=FASTMATH, cache=False, parallel=True)
def _poly_diff(p: np.ndarray, var: int, degree: int, psi, clmo, encode_dict_list) -> np.ndarray:
    """
    Compute the partial derivative of a polynomial with respect to a variable.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial
    var : int
        Index of the variable to differentiate with respect to (0 to N_VARS-1)
    degree : int
        Degree of the polynomial
    psi : numpy.ndarray
        Combinatorial table from init_index_tables
    clmo : numba.typed.List
        List of arrays containing packed multi-indices
    encode_dict_list : numba.typed.List
        List of dictionaries mapping packed multi-indices to their positions
        
    Returns
    -------
    numpy.ndarray
        Coefficient array of the differentiated polynomial
        
    Notes
    -----
    This function implements parallel computation of polynomial differentiation
    using a thread-safe approach. The output polynomial will have degree
    (degree - 1) unless the input is a constant polynomial (degree = 0), 
    in which case the output will also be degree 0 (constant zero).
    """
    # Degree-0 polynomial has zero derivative
    if degree == 0:
        out_size = psi[N_VARS, 0]
        return np.zeros(out_size, dtype=p.dtype)

    out_size = psi[N_VARS, degree - 1]

    # Allocate a private accumulation buffer for each thread
    nT = get_num_threads()
    scratch = np.zeros((nT, out_size), dtype=p.dtype)

    scratch_exp = np.empty(6, dtype=np.int64)           # ← NEW  (one per thread chunk)
    for i in prange(p.shape[0]):
        tid = get_thread_id()

        coeff = p[i]
        if coeff == 0:
            continue

        k_vec = np.empty(6, dtype=np.int64)
        fill_exponents(i, degree, clmo, k_vec)   # mutable view

        exp = k_vec[var]
        if exp == 0:
            continue

        k_vec[var] = exp - 1                     # safe mutation
        idx = encode_multiindex(k_vec, degree - 1, encode_dict_list)
        if idx != -1:
            scratch[tid, idx] += coeff * exp  # race-free write
        scratch_exp[var] = exp                # restore for next iteration

    # Reduction: sum the thread-local arrays into the final output
    dp = np.zeros(out_size, dtype=p.dtype)
    for tid in range(nT):
        dp += scratch[tid]

    return dp

@njit(fastmath=FASTMATH, cache=False)
def _poly_poisson(p: np.ndarray, deg_p: int, q: np.ndarray, deg_q: int, psi, clmo, encode_dict_list) -> np.ndarray:
    """
    Compute the Poisson bracket of two polynomials.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the first polynomial
    deg_p : int
        Degree of the first polynomial
    q : numpy.ndarray
        Coefficient array of the second polynomial
    deg_q : int
        Degree of the second polynomial
    psi : numpy.ndarray
        Combinatorial table from init_index_tables
    clmo : numba.typed.List
        List of arrays containing packed multi-indices
    encode_dict_list : numba.typed.List
        List of dictionaries mapping packed multi-indices to their positions
        
    Returns
    -------
    numpy.ndarray
        Coefficient array of the Poisson bracket {p, q}
        
    Notes
    -----
    The Poisson bracket {p, q} is defined as:
    
    {p, q} = Σ_{i=1}^3 (∂p/∂q_i * ∂q/∂p_i - ∂p/∂p_i * ∂q/∂q_i)
    
    where q_i are position variables and p_i are momentum variables.
    
    The output polynomial will have degree deg_p + deg_q - 2, unless
    one of the inputs is a constant, in which case the result is zero.
    """
    if deg_p == 0 or deg_q == 0:
        deg_r_temp = deg_p + deg_q - 2
        if deg_r_temp < 0: deg_r_temp = 0
        return np.zeros(psi[N_VARS, 0], dtype=p.dtype) 

    deg_r = deg_p + deg_q - 2
    if deg_r < 0:
        deg_r = 0

    r = np.zeros(psi[N_VARS, deg_r], dtype=p.dtype)
    for m in range(3):
        if deg_p >= 1:
            dpx = _poly_diff(p, m, deg_p, psi, clmo, encode_dict_list)
        else:
            dpx = np.zeros(psi[N_VARS, 0], dtype=p.dtype)
        
        if deg_q >= 1:
            dqqp = _poly_diff(q, m+3, deg_q, psi, clmo, encode_dict_list)
        else:
            dqqp = np.zeros(psi[N_VARS, 0], dtype=q.dtype)

        deg_dpx = max(0, deg_p-1)
        deg_dqqp = max(0, deg_q-1)

        term1 = _poly_mul(dpx, deg_dpx, dqqp, deg_dqqp, psi, clmo, encode_dict_list)
        if term1.shape[0] == r.shape[0]:
            # vectorised addition (no explicit loop needed)
            r += term1

        if deg_p >= 1:
            dpq = _poly_diff(p, m+3, deg_p, psi, clmo, encode_dict_list)
        else:
            dpq = np.zeros(psi[N_VARS,0], dtype=p.dtype)

        if deg_q >= 1:
            dqx = _poly_diff(q, m, deg_q, psi, clmo, encode_dict_list)
        else:
            dqx = np.zeros(psi[N_VARS,0], dtype=q.dtype)
        
        deg_dpq = max(0, deg_p-1)
        deg_dqx = max(0, deg_q-1)

        term2 = _poly_mul(dpq, deg_dpq, dqx, deg_dqx, psi, clmo, encode_dict_list)
        if term2.shape[0] == r.shape[0]:
            # vectorised subtraction
            r -= term2
    return r

@njit(fastmath=FASTMATH, cache=True)
def _get_degree(p: np.ndarray, psi) -> int:
    """
    Determine the degree of a polynomial from its coefficient array length.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial
    psi : numpy.ndarray
        Combinatorial table from init_index_tables
        
    Returns
    -------
    int
        The degree of the polynomial, or -1 if the coefficient array size
        doesn't match any expected size in the psi table
        
    Notes
    -----
    This function works by comparing the length of the coefficient array
    with the expected sizes for each degree from the psi table.
    """
    num_coeffs = p.shape[0]
    if num_coeffs == 0: # Should not happen for valid polynomials
        return -1 
    
    # N_VARS is imported from algorithms.variables
    # psi.shape[1] is max_degree + 1
    for d in range(psi.shape[1]): 
        if psi[N_VARS, d] == num_coeffs:
            return d
    return -1 # Should not be reached if poly and psi are consistent

@njit(fastmath=FASTMATH, cache=True)
def _poly_clean_inplace(p: np.ndarray, tol: float) -> None:
    """
    Set coefficients with absolute value below tolerance to zero (in-place).
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial to clean
    tol : float
        Tolerance threshold; coefficients with |value| <= tol will be set to zero
        
    Returns
    -------
    None
        The array 'p' is modified in-place
        
    Notes
    -----
    This function operates in-place, modifying the input array directly.
    Use _poly_clean for an out-of-place version.
    """
    for i in range(p.shape[0]):
        # np.abs works for real or complex types under numba
        if np.abs(p[i]) <= tol:
            p[i] = 0

@njit(fastmath=FASTMATH, cache=True)
def _poly_clean(p: np.ndarray, tol: float, out: np.ndarray) -> None:
    """
    Set coefficients with absolute value below tolerance to zero (out-of-place).
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial to clean
    tol : float
        Tolerance threshold; coefficients with |value| <= tol will be set to zero
    out : numpy.ndarray
        Output array where the result will be stored
        
    Returns
    -------
    None
        The result is stored in the 'out' array
        
    Notes
    -----
    This function creates a cleaned copy of the input array in 'out'.
    Use _poly_clean_inplace for an in-place version.
    """
    for i in range(p.shape[0]):
        if np.abs(p[i]) <= tol:
            out[i] = 0
        else:
            out[i] = p[i]

@njit(fastmath=FASTMATH, cache=True)
def _poly_evaluate(
    p: np.ndarray, 
    degree: int, 
    point: np.ndarray, 
    clmo: List[np.ndarray]
) -> np.complex128:
    """
    Evaluate a polynomial at a specific point.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial
    degree : int
        Degree of the polynomial
    point : numpy.ndarray
        Array of length N_VARS containing the values of variables
        where the polynomial should be evaluated
    clmo : numba.typed.List
        List of arrays containing packed multi-indices
        
    Returns
    -------
    numpy.complex128
        The value of the polynomial at the specified point
        
    Notes
    -----
    This function evaluates the polynomial by unpacking each coefficient's
    multi-index, computing the corresponding monomial value, and accumulating
    the result. The output is always complex to handle both real and complex
    polynomials.
    """

    if p.shape[0] == 0:
        return 0.0 + 0.0j

    pow_table = np.empty((N_VARS, degree + 1), dtype=point.dtype)
    for v in range(N_VARS):
        pow_table[v, 0] = 1.0 + 0.0j
        base = point[v]
        for e in range(1, degree + 1):
            pow_table[v, e] = pow_table[v, e - 1] * base

    current_sum = 0.0 + 0.0j
    for i in range(p.shape[0]):
        coeff_val = p[i]
        if coeff_val == 0.0 + 0.0j:
            continue

        exps = decode_multiindex(i, degree, clmo)   # immutable 6-tuple

        term_val = 1.0 + 0.0j
        for v in range(N_VARS):
            term_val *= pow_table[v, exps[v]]

        current_sum += coeff_val * term_val

    return current_sum

@njit(fastmath=FASTMATH, cache=True)
def _evaluate_reduced_monomial(
    k: np.ndarray,
    coords: np.ndarray, 
    var_idx: int,
    exp_change: int
) -> np.complex128:
    """Evaluate monomial x^k at coords with exponent of var_idx changed by exp_change."""
    result = 1.0 + 0.0j
    
    for i in range(6):
        exp = k[i]
        if i == var_idx:
            exp += exp_change
            
        if exp > 0:
            if abs(coords[i]) > 1e-15:
                result *= coords[i] ** exp
            else:
                return 0.0 + 0.0j  # Zero coordinate with positive exponent
        # exp == 0: multiply by 1 (no-op)
                
    return result

@njit(fastmath=FASTMATH, cache=True)
def _poly_integrate(p: np.ndarray, var: int, degree: int, psi, clmo, encode_dict_list) -> np.ndarray:
    """
    Integrate a polynomial with respect to one variable.
    
    Parameters
    ----------
    p : numpy.ndarray
        Coefficient array of the polynomial
    var : int
        Index of the variable to integrate with respect to (0 to N_VARS-1)
    degree : int
        Degree of the polynomial
    psi : numpy.ndarray
        Combinatorial table from init_index_tables
    clmo : numba.typed.List
        List of arrays containing packed multi-indices
    encode_dict_list : numba.typed.List
        List of dictionaries mapping packed multi-indices to their positions
        
    Returns
    -------
    numpy.ndarray
        Coefficient array of the integrated polynomial
        
    Notes
    -----
    The output polynomial will have degree (degree + 1).
    The integration constant is set to zero.
    """
    out_degree = degree + 1
    out_size = psi[N_VARS, out_degree]
    ip = np.zeros(out_size, dtype=p.dtype)

    for i in range(p.shape[0]):
        coeff = p[i]
        if coeff == 0:
            continue

        k_vec = np.empty(6, dtype=np.int64)
        fill_exponents(i, degree, clmo, k_vec)

        k_integrated = k_vec.copy()
        k_integrated[var] += 1

        new_coeff = coeff / (k_vec[var] + 1)

        idx = encode_multiindex(k_integrated, out_degree, encode_dict_list)
        if idx != -1:
            ip[idx] += new_coeff

    return ip
