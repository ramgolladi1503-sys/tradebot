"""Deterministic Gaussian Radial Basis Function Network (RBFN).

Scikit-learn free implementation using NumPy only.
Features:
- Deterministic quantile-spaced centers across sorted training data
- Closed-form Ridge-regularized weight solving: W = (Phi^T Phi + lambda I)^-1 Phi^T Y
- Proper bias term (ones column in Phi)
- Multidimensional input and target support
"""
from __future__ import annotations

from typing import Optional
import numpy as np


class GaussianRBFNetwork:
    """Radial Basis Function Network with Gaussian kernels and Ridge regularization.

    Parameters
    ----------
    n_centers : int
        Number of RBF centers. Default is 28.
    width : float
        Kernel width parameter (sigma). Default is 3.4.
    ridge : float
        Ridge regularization penalty lambda on kernel weights. Default is 4.0.
    """

    def __init__(
        self,
        n_centers: int = 28,
        width: float = 3.4,
        ridge: float = 4.0,
    ) -> None:
        if n_centers <= 0:
            raise ValueError("n_centers must be positive")
        if width <= 0:
            raise ValueError("width must be positive")
        if ridge < 0:
            raise ValueError("ridge must be non-negative")

        self.n_centers = int(n_centers)
        self.width = float(width)
        self.ridge = float(ridge)

        self.mu: Optional[np.ndarray] = None
        self.sigma: Optional[np.ndarray] = None
        self.centers: Optional[np.ndarray] = None
        self.weights: Optional[np.ndarray] = None
        self.is_fitted: bool = False

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        """Z-score normalize features using fitted mu and sigma, clipped to [-4, 4]."""
        if self.mu is None or self.sigma is None:
            raise ValueError("Model is not fitted; normalization statistics unavailable.")
        return np.clip((x - self.mu) / self.sigma, -4.0, 4.0)

    def _design_matrix(self, x: np.ndarray) -> np.ndarray:
        """Compute the design matrix Phi including bias (ones) and Gaussian activations."""
        if self.centers is None:
            raise ValueError("Model is not fitted; centers are undefined.")
        xn = self._normalize(x)
        # Pairwise squared Euclidean distance: (N, 1, D) - (1, K, D) -> (N, K)
        dist2 = np.sum((xn[:, None, :] - self.centers[None, :, :]) ** 2, axis=2)
        # Gaussian kernel: exp(-dist^2 / (2 * width^2))
        phi_rbf = np.exp(-dist2 / (2.0 * (self.width ** 2)))
        # Prepend bias column of ones
        ones = np.ones((len(x), 1), dtype=float)
        return np.column_stack([ones, phi_rbf])

    def fit(self, x: np.ndarray | list, y: np.ndarray | list) -> GaussianRBFNetwork:
        """Fit the RBF network weights using quantile centers and Ridge regression.

        Parameters
        ----------
        x : array-like of shape (N, D)
            Training input features.
        y : array-like of shape (N, M) or (N,)
            Training targets.

        Returns
        -------
        self : GaussianRBFNetwork
        """
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)

        if x_arr.ndim == 1:
            x_arr = x_arr.reshape(-1, 1)

        y_is_1d = (y_arr.ndim == 1)
        if y_is_1d:
            y_arr = y_arr.reshape(-1, 1)

        n_samples, n_features = x_arr.shape
        if n_samples < self.n_centers:
            raise ValueError(
                f"Number of samples ({n_samples}) must be >= n_centers ({self.n_centers})"
            )
        if n_samples != len(y_arr):
            raise ValueError(
                f"x samples ({n_samples}) must match y samples ({len(y_arr)})"
            )

        # Compute mean and std for normalization
        self.mu = np.mean(x_arr, axis=0)
        self.sigma = np.std(x_arr, axis=0, ddof=0)
        self.sigma[self.sigma == 0.0] = 1.0

        xn = self._normalize(x_arr)

        # Deterministic quantile-spaced centers
        # idx = floor((j + 0.5) * N / n_centers)
        idx = [int(np.floor((j + 0.5) * n_samples / self.n_centers)) for j in range(self.n_centers)]
        self.centers = xn[idx, :]

        # Design matrix Phi: shape (N, 1 + n_centers)
        phi = self._design_matrix(x_arr)

        # Ridge regularized closed-form solve:
        # Bias weight (index 0) has 0 regularization, while kernel weights have self.ridge
        reg = np.diag([0.0] + [self.ridge] * self.n_centers)
        lhs = phi.T @ phi + reg
        rhs = phi.T @ y_arr

        # Solve lhs @ weights = rhs
        self.weights = np.linalg.solve(lhs, rhs)
        self.is_fitted = True
        return self

    def predict(self, x: np.ndarray | list) -> np.ndarray:
        """Predict targets for new samples x.

        Parameters
        ----------
        x : array-like of shape (N, D) or (D,)

        Returns
        -------
        np.ndarray of shape (N, M) or (M,)
        """
        if not self.is_fitted or self.weights is None:
            raise RuntimeError("Cannot predict with unfitted GaussianRBFNetwork")

        x_arr = np.asarray(x, dtype=float)
        is_single = (x_arr.ndim == 1)
        if is_single:
            x_arr = x_arr.reshape(1, -1)

        phi = self._design_matrix(x_arr)
        pred = phi @ self.weights

        if pred.shape[1] == 1:
            pred = pred.reshape(-1)

        if is_single:
            return pred[0] if pred.ndim == 1 else pred[0, :]
        return pred
