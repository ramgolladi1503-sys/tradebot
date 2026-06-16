import numpy as np

class GaussianHMM:
    """
    Gaussian Hidden Markov Model (HMM) for Regime Classification.
    Provides probabilistic state detection for market regimes.
    """
    def __init__(self, n_components=2, n_iter=100, tol=1e-4):
        self.n_components = n_components
        self.n_iter = n_iter
        self.tol = tol
        
        # Parameters
        self.startprob_ = None
        self.transmat_ = None
        self.means_ = None
        self.covars_ = None
        self.is_fitted = False
        
    def _init_params(self, X):
        n_samples, n_features = X.shape
        self.startprob_ = np.ones(self.n_components) / self.n_components
        self.transmat_ = np.ones((self.n_components, self.n_components)) / self.n_components
        
        # Initialize means randomly from data
        indices = np.random.choice(n_samples, self.n_components, replace=True)
        self.means_ = X[indices]
        
        # Initialize covars as sample covariance
        cov = np.cov(X.T)
        if n_features == 1:
            cov = np.array([[cov]])
            self.covars_ = np.array([cov for _ in range(self.n_components)])
        else:
            self.covars_ = np.array([cov for _ in range(self.n_components)])

    def _compute_log_likelihood(self, X):
        n_samples, n_features = X.shape
        log_prob = np.zeros((n_samples, self.n_components))
        
        for c in range(self.n_components):
            mean = self.means_[c]
            cov = self.covars_[c]
            # Add small regularization to cov to prevent singular matrix
            cov = cov + np.eye(n_features) * 1e-6
            
            diff = X - mean
            inv_cov = np.linalg.inv(cov)
            
            # log(N(x | mean, cov))
            exponent = -0.5 * np.sum(diff @ inv_cov * diff, axis=1)
            norm_const = -0.5 * (n_features * np.log(2 * np.pi) + np.log(np.linalg.det(cov)))
            log_prob[:, c] = norm_const + exponent
            
        return log_prob
        
    def fit(self, X):
        """
        Simplified EM algorithm for fitting the Gaussian HMM.
        """
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
            
        n_samples, n_features = X.shape
        self._init_params(X)
        
        for _ in range(self.n_iter):
            log_prob = self._compute_log_likelihood(X)
            
            # E-step
            max_log_prob = np.max(log_prob, axis=1, keepdims=True)
            prob = np.exp(log_prob - max_log_prob)
            resp = prob / np.sum(prob, axis=1, keepdims=True)
            
            # M-step
            Nk = np.sum(resp, axis=0)
            self.means_ = (resp.T @ X) / Nk[:, np.newaxis]
            
            for c in range(self.n_components):
                diff = X - self.means_[c]
                cov = (resp[:, c:c+1] * diff).T @ diff / Nk[c]
                self.covars_[c] = cov
                
        self.is_fitted = True
        return self

    def predict(self, X):
        """Predict the most likely hidden state sequence."""
        if not self.is_fitted:
            raise ValueError("Model is not fitted yet.")
            
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
            
        log_prob = self._compute_log_likelihood(X)
        return np.argmax(log_prob, axis=1)
        
    def predict_proba(self, X):
        """Return posterior probabilities of each state."""
        if not self.is_fitted:
            raise ValueError("Model is not fitted yet.")
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        log_prob = self._compute_log_likelihood(X)
        max_log_prob = np.max(log_prob, axis=1, keepdims=True)
        prob = np.exp(log_prob - max_log_prob)
        return prob / np.sum(prob, axis=1, keepdims=True)
