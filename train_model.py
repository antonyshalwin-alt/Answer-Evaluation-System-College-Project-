# save as train_model.py and run once
import joblib
from sklearn.ensemble import RandomForestRegressor

# simple training data (similarity → marks)
X = [[0.1],[0.3],[0.5],[0.7],[0.9],[1.0]]
y = [1,3,5,7,9,10]

model = RandomForestRegressor()
model.fit(X,y)

joblib.dump(model,"ml_grading_model.pkl")
print("Model trained")