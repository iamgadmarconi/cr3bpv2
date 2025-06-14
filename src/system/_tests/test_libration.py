import numpy as np
import pytest
import symengine as se

from system.libration import (CONTINUOUS_SYSTEM, DISCRETE_SYSTEM,
                              CollinearPoint, L1Point, L2Point, L3Point,
                              L4Point, L5Point, LibrationPoint, LinearData,
                              TriangularPoint)

# --- Constants for testing ---
TEST_MU_EARTH_MOON = 0.01215  # Earth-Moon system
TEST_MU_SUN_EARTH = 3.00348e-6  # Sun-Earth system
TEST_MU_SUN_JUPITER = 9.5387e-4  # Sun-Jupiter system
TEST_MU_UNSTABLE = 0.04  # Above Routh's critical value for triangular points

# --- Helper functions ---
def is_symplectic(matrix, tol=1e-10):
    """
    Check if a 6x6 matrix is symplectic by verifying M^T J M = J
    where J is the standard symplectic matrix.
    """
    # Standard symplectic matrix J
    J = np.zeros((6, 6))
    n = 3  # 3 degrees of freedom
    for i in range(n):
        J[i, i+n] = 1
        J[i+n, i] = -1
    
    # Calculate M^T J M
    M_T_J_M = matrix.T @ J @ matrix
    
    # Check if M^T J M = J
    return np.allclose(M_T_J_M, J, atol=tol)

# --- Pytest Fixtures ---
@pytest.fixture
def l1_earth_moon():
    return L1Point(TEST_MU_EARTH_MOON)

@pytest.fixture
def l2_earth_moon():
    return L2Point(TEST_MU_EARTH_MOON)

@pytest.fixture
def l3_earth_moon():
    return L3Point(TEST_MU_EARTH_MOON)

@pytest.fixture
def l4_earth_moon():
    return L4Point(TEST_MU_EARTH_MOON)

@pytest.fixture
def l5_earth_moon():
    return L5Point(TEST_MU_EARTH_MOON)

@pytest.fixture
def l1_sun_earth():
    return L1Point(TEST_MU_SUN_EARTH)

@pytest.fixture
def l2_sun_earth():
    return L2Point(TEST_MU_SUN_EARTH)

@pytest.fixture
def l3_sun_jupiter():
    return L3Point(TEST_MU_SUN_JUPITER)

@pytest.fixture
def l4_unstable():
    return L4Point(TEST_MU_UNSTABLE)

# --- Test Functions ---
def test_libration_point_initialization():
    """Test initialization of different libration points."""
    # Test with several mu values
    l1_earth_moon = L1Point(TEST_MU_EARTH_MOON)
    assert l1_earth_moon.mu == TEST_MU_EARTH_MOON
    
    l2_sun_earth = L2Point(TEST_MU_SUN_EARTH)
    assert l2_sun_earth.mu == TEST_MU_SUN_EARTH
    
    l3_sun_jupiter = L3Point(TEST_MU_SUN_JUPITER)
    assert l3_sun_jupiter.mu == TEST_MU_SUN_JUPITER
    
    l4_earth_moon = L4Point(TEST_MU_EARTH_MOON)
    assert l4_earth_moon.mu == TEST_MU_EARTH_MOON
    
    l5_sun_earth = L5Point(TEST_MU_SUN_EARTH)
    assert l5_sun_earth.mu == TEST_MU_SUN_EARTH

def test_positions(l1_earth_moon, l2_earth_moon, l3_earth_moon, l4_earth_moon, l5_earth_moon):
    """Test computation of libration point positions."""
    # L1 position should be between primaries (-mu < x < 1-mu)
    pos_l1 = l1_earth_moon.position
    assert -TEST_MU_EARTH_MOON < pos_l1[0] < 1-TEST_MU_EARTH_MOON
    assert np.isclose(pos_l1[1], 0)
    assert np.isclose(pos_l1[2], 0)
    
    # L2 position should be beyond smaller primary (x > 1-mu)
    pos_l2 = l2_earth_moon.position
    assert pos_l2[0] > 1-TEST_MU_EARTH_MOON
    assert np.isclose(pos_l2[1], 0)
    assert np.isclose(pos_l2[2], 0)
    
    # L3 position should be beyond larger primary (x < -mu)
    pos_l3 = l3_earth_moon.position
    assert pos_l3[0] < -TEST_MU_EARTH_MOON
    assert np.isclose(pos_l3[1], 0)
    assert np.isclose(pos_l3[2], 0)
    
    # L4 position should form equilateral triangle (60° above x-axis)
    pos_l4 = l4_earth_moon.position
    assert np.isclose(pos_l4[0], 0.5-TEST_MU_EARTH_MOON)
    assert np.isclose(pos_l4[1], np.sqrt(3)/2)
    assert np.isclose(pos_l4[2], 0)
    
    # L5 position should form equilateral triangle (60° below x-axis)
    pos_l5 = l5_earth_moon.position
    assert np.isclose(pos_l5[0], 0.5-TEST_MU_EARTH_MOON)
    assert np.isclose(pos_l5[1], -np.sqrt(3)/2)
    assert np.isclose(pos_l5[2], 0)

def test_gamma_values(l1_earth_moon, l2_earth_moon, l3_earth_moon):
    """Test gamma (distance ratio) calculations for collinear points."""
    # For L1, gamma should be positive and small
    gamma_l1 = l1_earth_moon.gamma
    assert gamma_l1 > 0
    assert gamma_l1 < 1.0
    
    # For L2, gamma should be positive and small
    gamma_l2 = l2_earth_moon.gamma
    assert gamma_l2 > 0
    assert gamma_l2 < 1.0
    
    # For L3, gamma should be positive and close to 1
    gamma_l3 = l3_earth_moon.gamma
    assert gamma_l3 > 0
    # L3 gamma is approximately 1 - (7/12)*mu
    expected_gamma_l3 = 1.0 - (7.0/12.0) * TEST_MU_EARTH_MOON
    assert np.isclose(gamma_l3, expected_gamma_l3, rtol=0.1)

def test_cn_coefficients(l1_earth_moon, l2_earth_moon, l3_earth_moon, l1_sun_earth, l2_sun_earth, l3_sun_jupiter):
    """Test calculation of cn coefficients for collinear points."""
    c2_l1_em = l1_earth_moon._cn(2)
    c2_l2_em = l2_earth_moon._cn(2)
    c2_l3_em = l3_earth_moon._cn(2)

    c2_l1_se = l1_sun_earth._cn(2)
    c2_l2_se = l2_sun_earth._cn(2)
    c2_l3_sj = l3_sun_jupiter._cn(2)

    assert c2_l1_em > 1.0
    assert c2_l2_em > 1.0
    assert c2_l3_em > 1.0

    assert c2_l1_se > 1.0
    assert c2_l2_se > 1.0
    assert c2_l3_sj > 1.0

def test_linear_modes(l1_earth_moon, l2_earth_moon, l3_earth_moon):
    """Test calculation of linear modes for collinear points.
    """
    # Test for L1 Point
    lambda1, omega1, omega2 = l1_earth_moon.linear_modes

    assert lambda1 > 0
    assert omega1 > 0
    assert omega2 > 0

    c2 = l1_earth_moon._cn(2)
    
    # Calculate the roots directly using the formula from the image
    discriminant = 9 * c2**2 - 8 * c2
    eta1 = (c2 - 2 - np.sqrt(discriminant)) / 2
    eta2 = (c2 - 2 + np.sqrt(discriminant)) / 2
    
    # Verify eta1 < 0 and eta2 > 0 as stated in the theory
    assert eta1 < 0, "Expected eta1 < 0 for collinear points"
    assert eta2 > 0, "Expected eta2 > 0 for collinear points"
    
    # Calculate expected values directly using the formulas
    expected_lambda1 = np.sqrt(eta2)
    expected_omega1 = np.sqrt(-eta1)
    expected_omega2 = np.sqrt(c2)
    
    # Verify that linear_modes returns values matching the analytical expressions
    assert np.isclose(lambda1, expected_lambda1, rtol=1e-5), f"lambda1 should be {expected_lambda1}, got {lambda1}"
    assert np.isclose(omega1, expected_omega1, rtol=1e-5), f"omega1 should be {expected_omega1}, got {omega1}"
    assert np.isclose(omega2, expected_omega2, rtol=1e-5), f"omega2 should be {expected_omega2}, got {omega2}"
    
    # Test for L2 Point
    lambda1_l2, omega1_l2, omega2_l2 = l2_earth_moon.linear_modes

    assert lambda1 > 0
    assert omega1 > 0
    assert omega2 > 0

    c2_l2 = l2_earth_moon._cn(2)
    
    discriminant_l2 = 9 * c2_l2**2 - 8 * c2_l2
    eta1_l2 = (c2_l2 - 2 - np.sqrt(discriminant_l2)) / 2
    eta2_l2 = (c2_l2 - 2 + np.sqrt(discriminant_l2)) / 2
    
    assert eta1_l2 < 0
    assert eta2_l2 > 0
    
    expected_lambda1_l2 = np.sqrt(eta2_l2)
    expected_omega1_l2 = np.sqrt(-eta1_l2)
    expected_omega2_l2 = np.sqrt(c2_l2)
    
    assert np.isclose(lambda1_l2, expected_lambda1_l2, rtol=1e-5)
    assert np.isclose(omega1_l2, expected_omega1_l2, rtol=1e-5)
    assert np.isclose(omega2_l2, expected_omega2_l2, rtol=1e-5)
    
    # Test for L3 Point
    lambda1_l3, omega1_l3, omega2_l3 = l3_earth_moon.linear_modes

    assert lambda1 > 0
    assert omega1 > 0
    assert omega2 > 0

    c2_l3 = l3_earth_moon._cn(2)
    
    discriminant_l3 = 9 * c2_l3**2 - 8 * c2_l3
    eta1_l3 = (c2_l3 - 2 - np.sqrt(discriminant_l3)) / 2
    eta2_l3 = (c2_l3 - 2 + np.sqrt(discriminant_l3)) / 2
    
    assert eta1_l3 < 0
    assert eta2_l3 > 0
    
    expected_lambda1_l3 = np.sqrt(eta2_l3)
    expected_omega1_l3 = np.sqrt(-eta1_l3)
    expected_omega2_l3 = np.sqrt(c2_l3)
    
    assert np.isclose(lambda1_l3, expected_lambda1_l3, rtol=1e-5)
    assert np.isclose(omega1_l3, expected_omega1_l3, rtol=1e-5)
    assert np.isclose(omega2_l3, expected_omega2_l3, rtol=1e-5)

def test_scale_factors(l1_earth_moon, l2_earth_moon, l3_earth_moon):
    """Test that scale factors s1 and s2 are always positive."""
    # Test for L1 Point
    lambda1, omega1, omega2 = l1_earth_moon.linear_modes
    s1, s2 = l1_earth_moon._scale_factor(lambda1, omega1)
    
    assert s1 > 0, "s1 scale factor should be positive"
    assert s2 > 0, "s2 scale factor should be positive"
    
    # Test for L2 Point
    lambda1_l2, omega1_l2, omega2_l2 = l2_earth_moon.linear_modes
    s1_l2, s2_l2 = l2_earth_moon._scale_factor(lambda1_l2, omega1_l2)
    
    assert s1_l2 > 0, "s1 scale factor should be positive for L2"
    assert s2_l2 > 0, "s2 scale factor should be positive for L2"
    
    # Test for L3 Point
    lambda1_l3, omega1_l3, omega2_l3 = l3_earth_moon.linear_modes
    s1_l3, s2_l3 = l3_earth_moon._scale_factor(lambda1_l3, omega1_l3)
    
    assert s1_l3 > 0, "s1 scale factor should be positive for L3"
    assert s2_l3 > 0, "s2 scale factor should be positive for L3"

def test_normal_form_transform(l1_earth_moon, l2_earth_moon, l3_earth_moon):
    """Test normal form transform for collinear points."""
    # Test for L1 Point
    C_l1, Cinv_l1 = l1_earth_moon.normal_form_transform()
    assert is_symplectic(C_l1)
    assert is_symplectic(Cinv_l1)

    # Test for L2 Point
    C_l2, Cinv_l2 = l2_earth_moon.normal_form_transform()
    assert is_symplectic(C_l2)
    assert is_symplectic(Cinv_l2)

    # Test for L3 Point
    C_l3, Cinv_l3 = l3_earth_moon.normal_form_transform()
    assert is_symplectic(C_l3)
    assert is_symplectic(Cinv_l3)
