import numpy as np

class KalmanFilter:
    """
    Kalman Filter implementation for Pairs Trading.
    Used to dynamically estimate the hedge ratio and spread intercept.
    """
    def __init__(self, delta=1e-4, wt=1e-4):
        """
        Initializes the Kalman Filter for a 2-variable regression (intercept and slope/hedge ratio).
        
        y = alpha + beta * x
        
        Args:
            delta (float): System noise for intercept and slope.
            wt (float): Measurement noise.
        """
        self.delta = delta
        self.wt = wt
        
        # State estimation [alpha, beta]
        self.theta = np.zeros(2)
        
        # Covariance matrix of state
        self.P = np.zeros((2, 2))
        
        # Measurement noise covariance
        self.R = np.array([[self.wt]])
        
        # System noise covariance
        self.Q = np.array([[self.delta, 0], [0, self.delta]])
        
        self.is_initialized = False

    def update(self, price_a, price_b):
        """
        Updates the Kalman Filter state.
        
        Args:
            price_a (float): The price of the dependent asset (y).
            price_b (float): The price of the independent asset (x).
            
        Returns:
            tuple: (hedge_ratio, intercept, estimated_error)
        """
        if price_a is None or price_b is None:
            return self.theta[1], self.theta[0], 0.0

        if not self.is_initialized:
            # First observation initialization
            # Naive initialization: intercept = 0, hedge_ratio = price_a / price_b
            hedge_ratio = price_a / price_b if price_b != 0 else 1.0
            self.theta = np.array([0.0, hedge_ratio])
            self.P = np.array([[1.0, 0], [0, 1.0]])
            self.is_initialized = True
            return self.theta[1], self.theta[0], 0.0

        # Measurement equation variables
        F = np.array([[1.0, price_b]]) # Observation matrix (1 x 2)
        y = np.array([[price_a]]) # Actual measurement (1 x 1)
        
        # Prediction Step
        # theta_t|t-1 = theta_t-1|t-1 (Random walk assumption for state)
        theta_pred = self.theta.copy()
        
        # P_t|t-1 = P_t-1|t-1 + Q
        P_pred = self.P + self.Q
        
        # Update Step
        # Measurement prediction error (innovation)
        y_pred = F.dot(theta_pred)
        e = y - y_pred # (1 x 1)
        
        # Measurement prediction covariance
        S = F.dot(P_pred).dot(F.T) + self.R # (1 x 1)
        
        # Kalman Gain
        K = P_pred.dot(F.T).dot(np.linalg.inv(S)) # (2 x 1)
        
        # State update
        self.theta = theta_pred + (K.dot(e)).flatten()
        
        # Covariance update
        self.P = P_pred - K.dot(F).dot(P_pred)
        
        # Return beta (hedge_ratio), alpha (intercept), and the error
        return self.theta[1], self.theta[0], e[0][0]
