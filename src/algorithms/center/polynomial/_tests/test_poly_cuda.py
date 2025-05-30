import numpy as np
import pytest
import symengine as se
from numba.typed import List

from algorithms.center.polynomial.base import (
    decode_multiindex, encode_multiindex, init_index_tables, make_poly,
    PSI_GLOBAL, CLMO_GLOBAL, ENCODE_DICT_GLOBAL
)
from algorithms.center.polynomial.cuda.evaluate import PolynomialEvaluatorCUDA
from algorithms.variables import N_VARS

# Initialize tables for tests
MAX_DEGREE = 5
PSI, CLMO = init_index_tables(MAX_DEGREE)

# Define Symengine variables for tests, matching N_VARS and typical order
if N_VARS == 6:
    s_vars = se.symbols(f'x0:{N_VARS}')
else:
    s_vars = se.symbols(','.join([f'x{i}' for i in range(N_VARS)]))

def create_symengine_poly(coeffs: np.ndarray, degree: int, sym_vars: list, psi, clmo) -> se.Expr:
    sym_poly = se.sympify(0)
    if coeffs.shape[0] == 0:
        return sym_poly
    for i in range(coeffs.shape[0]):
        coeff_val = coeffs[i]
        if coeff_val == 0:
            continue
        exponents = decode_multiindex(i, degree, clmo)
        term = se.sympify(coeff_val)
        for var_idx in range(N_VARS):
            if exponents[var_idx] > 0:
                term *= (sym_vars[var_idx] ** exponents[var_idx])
        sym_poly += term
    return sym_poly

def evaluate_symengine_poly(sym_poly: se.Expr, point_map: dict) -> complex:
    return complex(sym_poly.subs(point_map).evalf())

@pytest.fixture(scope="module")
def cuda_evaluator_fixture(): # Renamed to avoid clash if a variable 'cuda_evaluator' is used
    # This fixture now returns a function that takes a list of polynomials
    # where each polynomial is a list of coefficient arrays by degree.
    return lambda poly_p_list: PolynomialEvaluatorCUDA(poly_p_list, CLMO)

@pytest.mark.parametrize("degree", range(MAX_DEGREE + 1))
def test_cuda_poly_evaluate_zero_polynomial(degree, cuda_evaluator_fixture):
    coeffs = make_poly(degree, PSI)  # all zeros
    point_vals = np.random.rand(1, N_VARS) + 1j * np.random.rand(1, N_VARS)
    
    # Construct the full list of coefficient arrays for one polynomial
    poly_list_for_cuda = [make_poly(d, PSI) for d in range(MAX_DEGREE + 1)]
    poly_list_for_cuda[degree] = coeffs # Place the test's coeffs at the correct degree index
    
    evaluator = cuda_evaluator_fixture([poly_list_for_cuda])
    cuda_result = evaluator.evaluate_single(0, point_vals)[0]
    assert np.isclose(cuda_result, 0.0 + 0.0j)

@pytest.mark.parametrize("degree", range(1, MAX_DEGREE + 1))
def test_cuda_poly_evaluate_single_monomial(degree, cuda_evaluator_fixture):
    coeffs = make_poly(degree, PSI)
    test_coeff_val = 2.5 - 1.5j
    k_test = np.zeros(N_VARS, dtype=np.int64)
    vars_to_use = min(N_VARS, degree)
    if vars_to_use > 0:
        deg_per_var = degree // vars_to_use
        remainder = degree % vars_to_use
        for i in range(vars_to_use):
            k_test[i] = deg_per_var
            if i < remainder:
                k_test[i] += 1
    idx = encode_multiindex(k_test, degree, ENCODE_DICT_GLOBAL)
    if idx != -1 and idx < coeffs.shape[0]:
        coeffs[idx] = test_coeff_val
    else:
        if coeffs.shape[0] > 0:
            coeffs[0] = test_coeff_val
            # k_test = decode_multiindex(0, degree, CLMO) # Not needed to reassign k_test here
        else:
            pytest.skip(f"No monomials for degree {degree} with N_VARS={N_VARS}")
    
    poly_list_for_cuda = [make_poly(d, PSI) for d in range(MAX_DEGREE + 1)]
    poly_list_for_cuda[degree] = coeffs
    
    point_vals_np = np.random.rand(1, N_VARS) * 2 - 1 + 1j * (np.random.rand(1, N_VARS) * 2 - 1)
    evaluator = cuda_evaluator_fixture([poly_list_for_cuda])
    cuda_result = evaluator.evaluate_single(0, point_vals_np)[0]
    
    # For Symengine comparison, we evaluate the homogeneous part directly
    sym_poly_expr = create_symengine_poly(coeffs, degree, s_vars, PSI, CLMO)
    point_map_sym = {s_vars[i]: point_vals_np[0, i] for i in range(N_VARS)}
    symengine_eval = evaluate_symengine_poly(sym_poly_expr, point_map_sym)
    
    assert np.isclose(cuda_result, symengine_eval, atol=1e-9, rtol=1e-9)

@pytest.mark.parametrize("degree", range(MAX_DEGREE + 1))
def test_cuda_poly_evaluate_multiple_terms(degree, cuda_evaluator_fixture):
    coeffs = make_poly(degree, PSI)
    num_coeffs_to_set = min(coeffs.shape[0], 5)
    if coeffs.shape[0] > 0: # Ensure choice is possible
        indices_to_set = np.random.choice(coeffs.shape[0], num_coeffs_to_set, replace=False)
        for i in indices_to_set:
            coeffs[i] = np.random.rand() - 0.5 + 1j * (np.random.rand() - 0.5)
    
    poly_list_for_cuda = [make_poly(d, PSI) for d in range(MAX_DEGREE + 1)]
    poly_list_for_cuda[degree] = coeffs
        
    point_vals_np = np.random.rand(1, N_VARS) + 1j * np.random.rand(1, N_VARS)
    evaluator = cuda_evaluator_fixture([poly_list_for_cuda])
    cuda_result = evaluator.evaluate_single(0, point_vals_np)[0]
    
    sym_poly_expr = create_symengine_poly(coeffs, degree, s_vars, PSI, CLMO)
    point_map_sym = {s_vars[i]: point_vals_np[0, i] for i in range(N_VARS)}
    symengine_eval = evaluate_symengine_poly(sym_poly_expr, point_map_sym)
    
    if degree == 0 and coeffs.shape[0] > 0:
        expected_val_deg0 = coeffs[0]
        assert np.isclose(cuda_result, expected_val_deg0)
        assert np.isclose(symengine_eval, expected_val_deg0)
    elif coeffs.shape[0] == 0: # No terms for this degree (e.g. psi[N_VARS, degree] is 0)
        assert np.isclose(cuda_result, 0.0 + 0.0j)
        assert np.isclose(symengine_eval, 0.0 + 0.0j)
    else:
        assert np.isclose(cuda_result, symengine_eval, atol=1e-9, rtol=1e-9)

def test_cuda_poly_evaluate_at_origin(cuda_evaluator_fixture):
    for loop_degree in range(MAX_DEGREE + 1):
        coeffs_for_loop_degree = make_poly(loop_degree, PSI)
        if coeffs_for_loop_degree.shape[0] > 0:
            coeffs_for_loop_degree[np.random.randint(0, coeffs_for_loop_degree.shape[0])] = 1.0 + 1.0j
        
        poly_list_for_cuda = [make_poly(d, PSI) for d in range(MAX_DEGREE + 1)]
        poly_list_for_cuda[loop_degree] = coeffs_for_loop_degree
        
        point_at_origin = np.zeros((1, N_VARS), dtype=np.complex128)
        evaluator = cuda_evaluator_fixture([poly_list_for_cuda])
        cuda_result = evaluator.evaluate_single(0, point_at_origin)[0]
        
        # Expected result for P(0)
        expected_at_origin = 0.0 + 0.0j
        if loop_degree == 0 and coeffs_for_loop_degree.shape[0] > 0:
            expected_at_origin = coeffs_for_loop_degree[0]
        
        assert np.isclose(cuda_result, expected_at_origin)

def test_cuda_poly_evaluate_point_with_zeros(cuda_evaluator_fixture):
    degree = 2 # Test with a specific degree
    if PSI[N_VARS, degree] == 0:
        pytest.skip("Not enough terms for degree 2 test")
        
    coeffs = make_poly(degree, PSI)
    # Example: P = x0^2 + x0*x1 + x1^2 (homogeneous degree 2)
    k_x0sq = np.array([2, 0, 0, 0, 0, 0], dtype=np.int64)
    k_x0x1 = np.array([1, 1, 0, 0, 0, 0], dtype=np.int64)
    k_x1sq = np.array([0, 2, 0, 0, 0, 0], dtype=np.int64)
    
    idx_x0sq = encode_multiindex(k_x0sq, degree, ENCODE_DICT_GLOBAL)
    idx_x0x1 = encode_multiindex(k_x0x1, degree, ENCODE_DICT_GLOBAL)
    idx_x1sq = encode_multiindex(k_x1sq, degree, ENCODE_DICT_GLOBAL)
    
    if idx_x0sq != -1 and idx_x0sq < coeffs.shape[0]: coeffs[idx_x0sq] = 1.0
    if idx_x0x1 != -1 and idx_x0x1 < coeffs.shape[0]: coeffs[idx_x0x1] = 1.0
    if idx_x1sq != -1 and idx_x1sq < coeffs.shape[0]: coeffs[idx_x1sq] = 1.0
    
    poly_list_for_cuda = [make_poly(d, PSI) for d in range(MAX_DEGREE + 1)]
    poly_list_for_cuda[degree] = coeffs
        
    point_vals_np = np.zeros((1, N_VARS), dtype=np.complex128)
    point_vals_np[0, 0] = 2.0 + 1j  # x0 = 2+j, other vars are 0
    
    # Expected: (2+j)^2 + (2+j)*0 + 0^2 = (2+j)^2 = 3 + 4j
    expected_eval_manual = (2.0 + 1j) ** 2
    
    evaluator = cuda_evaluator_fixture([poly_list_for_cuda])
    cuda_result = evaluator.evaluate_single(0, point_vals_np)[0]
    
    # Symengine evaluation for the homogeneous part
    sym_poly_expr = create_symengine_poly(coeffs, degree, s_vars, PSI, CLMO)
    point_map_sym = {s_vars[i]: point_vals_np[0, i] for i in range(N_VARS)}
    symengine_eval = evaluate_symengine_poly(sym_poly_expr, point_map_sym)
    
    assert np.isclose(cuda_result, expected_eval_manual)
    assert np.isclose(symengine_eval, expected_eval_manual) # Symengine should also match manual
    assert np.isclose(cuda_result, symengine_eval) # And CUDA result should match Symengine
