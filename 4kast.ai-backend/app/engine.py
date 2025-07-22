# app/engine.py

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' # Suppresses INFO and WARNING logs
os.environ['CUDA_VISIBLE_DEVICES'] = '-1' # Tells TensorFlow to use CPU only

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Request, Form, status, Path, Query
from fastapi.responses import FileResponse, Response, JSONResponse
import plotly.graph_objects as go
from .security import get_current_user, create_access_token, verify_password
from fastapi.security import OAuth2PasswordRequestForm
from .db import get_hana_connection
from pmdarima import auto_arima
from tensorflow.keras.layers import LSTM, Dense
from statsmodels.tsa.api import VAR, VARMAX
from tensorflow.keras.models import Sequential
from statsmodels.tsa.ar_model import AutoReg
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error, mean_absolute_error
from sklearn.model_selection import train_test_split
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel, ExpSineSquared
from app.models import LoginRequest, ForecastInput, UploadCleanedData, DeleteFileRequest, UserCreate, UserOut, ActualsUpdate, SaveActualsRequest, CustomHoliday, HolidayConfig
from fastapi.responses import FileResponse
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from sklearn.gaussian_process import GaussianProcessRegressor
from urllib.parse import unquote
import os
import io
import streamlit as st
import matplotlib.pyplot as plt
import csv as csv_module
import json
import pandas as pd
import shutil
from urllib.parse import unquote
from typing import List, Dict, Optional
from io import StringIO
import numpy as np
from statsmodels.tsa.stattools import adfuller, acf, pacf
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing
from prophet import Prophet
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.layers import GRU, Dropout
import tensorflow as tf
import re
from datetime import datetime, timedelta
from datetime import date
import glob
from pydantic import BaseModel, constr, EmailStr
import seaborn as sns
import plotly.express as px
from .config import OrganizationCalendarConfig
import pprint
from typing import Optional
import traceback
from decimal import Decimal
from passlib.hash import bcrypt
import holidays

router = APIRouter(prefix="/api/engine", tags=["engine"])
@router.get("/status")

def engine_status(
    current_user: str = Depends(get_current_user),
    conn = Depends(get_hana_connection)
):
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM USERS")
        count = cur.fetchone()[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HANA error: {e}")
    return {

        "engine": "MyAwesomeEngine",
        "status": "running",
        "hana_dummy_row_count": count,
        "user": current_user
    }

@router.post("/test")
def function1():
    return{
        "test": "success"
    }

UPLOAD_DIR = "uploaded_files"

@router.post("/upload-cleaned-data")
async def upload_cleaned_data(
    file: UploadFile = File(...),
    granularity: Optional[str] = Form("Overall"),
    timeBucket: Optional[str] = Form("Daily"),
    forecastHorizon: Optional[int] = Form(30),
    columnMappings: Optional[str] = Form("{}"),
    timeDependentVariables: Optional[str] = Form("[]"),
    organizationId: Optional[str] = Form("default"),  # Add organization ID parameter
    current_user: str = Depends(get_current_user), 
    conn = Depends(get_hana_connection)
):
    try:
        filename = file.filename
        content = await file.read()

        try:
            csv_text = content.decode("utf-8")
            df = pd.read_csv(StringIO(csv_text))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

        # Validate required columns
        required_columns = ['Date', 'Demand']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(status_code=400, detail=f"Missing required columns: {missing_columns}")

        # Convert string form fields into usable Python objects
        try:
            column_mappings_dict = json.loads(columnMappings)
        except json.JSONDecodeError:
            column_mappings_dict = {}

        try:
            time_dependent_variables_list = json.loads(timeDependentVariables)
        except json.JSONDecodeError:
            time_dependent_variables_list = []

        try:
            df, summary = process_uploaded_data(
                df,
                granularity,
                timeBucket,
                forecastHorizon,
                column_mappings_dict,
                organizationId  # Pass organization ID to processing function
            )

            # Save processed file
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            file_path = os.path.join(UPLOAD_DIR, filename)
            df.to_csv(file_path, index=False)

            # Save metadata
            metadata_path = os.path.join(UPLOAD_DIR, os.path.splitext(filename)[0] + "_metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(summary, f)
            
            data_json = df.to_json(orient="records")
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO "DBADMIN"."HISTORICALDATA_STAGE" ("DATA_JSON") VALUES (?)',
                    (data_json,)
                )
                conn.commit()
                cur.execute('SELECT CURRENT_IDENTITY_VALUE() FROM "DBADMIN"."HISTORICALDATA_STAGE"')
                runid = cur.fetchone()[0]

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"File '{filename}' processed successfully",
                    "filename": filename,
                    "summary": summary,
                    "runid": runid
                }
            )

        except Exception as e:
            traceback_str = traceback.format_exc()
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": f"Error processing data: {str(e)}",
                    "traceback": traceback_str
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Unexpected error: {str(e)}"}
        )

# Function to determine item_col based on forecast type
def determine_item_col(df, forecast_type):
    """Determines the appropriate item_col based on forecast type and available columns"""
    if forecast_type == "Item-wise":
        if "ProductID" in df.columns:
            return "ProductID"
    elif forecast_type == "Store-Item Combination":
        if "StoreID" in df.columns and "ProductID" in df.columns:
            # Create store_item column if it doesn't exist
            if "store_item" not in df.columns:
                df["store_item"] = df["StoreID"].astype(str) + " - " + df["ProductID"].astype(str)
            return "store_item"
    return None

# Update the data preprocessing section in the /upload-cleaned-data endpoint handler
def process_uploaded_data(df, granularity, time_bucket, forecast_horizon, column_mappings, organization_id='default'):
    try:
        # Clean up granularity and time bucket values
        granularity = granularity.strip() if isinstance(granularity, str) else granularity
        time_bucket = time_bucket.strip() if isinstance(time_bucket, str) else time_bucket
        
        print(f"Processing data with time_bucket: {time_bucket}, granularity: {granularity}")
        
        # Map granularity to forecast_type
        forecast_type = map_granularity_to_forecast_type(granularity)
        
        # Determine item_col based on forecast_type
        item_col = determine_item_col(df, forecast_type)
        
        # PERFORM AGGREGATION HERE
        if time_bucket and time_bucket != "Daily":
            print(f"Applying {time_bucket} aggregation...")
            df = aggregate_data(df, time_bucket, forecast_type, item_col, organization_id)
            print(f"Aggregation completed. New shape: {df.shape}")
        else:
            print("No aggregation applied - using Daily data")
        
        # Create summary
        stats = {
            "mean": float(df["Demand"].mean()),
            "median": float(df["Demand"].median()),
            "min": float(df["Demand"].min()),
            "max": float(df["Demand"].max()),
            "std": float(df["Demand"].std())
        }
        
        summary = {
            "originalColumns": df.columns.tolist(),
            "rowCount": len(df),
            "granularity": granularity,
            "timeBucket": time_bucket,
            "forecastHorizon": forecast_horizon,
            "item_col": item_col,
            "dataFrequency": api_infer_frequency(df),
            "seasonality": api_detect_seasonality(df),
            "dataStats": stats,
            "processedColumns": df.columns.tolist(),
            "forecast_type": forecast_type,
            "aggregationApplied": time_bucket != "Daily"
        }
        
        return df, summary
    except Exception as e:
        print(f"Error in data preprocessing: {str(e)}")
        raise ValueError(f"Data preprocessing failed: {str(e)}")
    
# Simplified version of detect_seasonality for API use
def api_detect_seasonality(df):
    """Detect seasonality patterns without Streamlit dependencies"""
    try:
        if len(df) < 4:
            print(f"Dataset too small ({len(df)} rows) for seasonality detection. Defaulting to period=7.")
            return 7

        if 'Date' not in df.columns or 'Demand' not in df.columns:
            print("Required columns 'Date' and 'Demand' must be present")
            return 7
            
        # Infer frequency from date index
        date_freq = api_infer_frequency(df)
        
        freq_based_period = {
            'D': 7,    # Daily -> Weekly seasonality
            'W': 52,   # Weekly -> Yearly seasonality
            'M': 12,   # Monthly -> Yearly seasonality
            'Q': 4,    # Quarterly -> Yearly seasonality
            'Y': 1     # Yearly -> No seasonality
        }.get(date_freq, 7)  # Default to weekly if unknown
        
        return freq_based_period
        
    except Exception as e:
        print(f"Error detecting seasonality: {str(e)}")
        return 7  # Default to weekly seasonality

# Simplified version of infer_frequency for API use
def api_infer_frequency(df, date_col='Date'):
    """Infer the frequency of time series data without Streamlit dependencies"""
    try:
        if date_col not in df.columns:
            print(f"'{date_col}' not found in DataFrame columns")
            return 'D'  # Default to daily
        
        # Get the datetime series
        dates = pd.Series(pd.to_datetime(df[date_col], errors='coerce').dropna().unique()).sort_values()
        
        if len(dates) < 2:
            print("Too few dates to infer frequency. Defaulting to 'D'.")
            return 'D'
        
        # Calculate differences between consecutive dates
        date_diffs = dates.diff().dt.days.dropna()
        
        if date_diffs.empty:
            print("No valid differences to infer frequency. Defaulting to 'D'.")
            return 'D'
        
        # Get the most common difference
        most_common_diff = date_diffs.mode()[0]
        
        # Map to frequency based on most common difference
        freq_map = {
            1: 'D',     # Daily
            7: 'W',     # Weekly
            14: 'W',    # Bi-weekly
            28: 'M',    # Monthly (28 days)
            30: 'M',    # Monthly (30 days)
            31: 'M',    # Monthly (31 days)
            90: 'Q',    # Quarterly (90 days)
            91: 'Q',    # Quarterly (91 days)
            92: 'Q',    # Quarterly (92 days)
            365: 'Y',   # Yearly (365 days)
            366: 'Y'    # Yearly (366 days - leap year)
        }
        
        closest_diff = min(freq_map.keys(), key=lambda k: abs(k - most_common_diff))       
        
        if abs(closest_diff - most_common_diff) <= 1:
            freq = freq_map.get(closest_diff, 'D')
        else:
            freq = 'D' # Default if no close match
        
        print(f"Inferred frequency: {freq} (most common diff: {most_common_diff} days)")
        return freq
        
    except Exception as e:
        print(f"Error inferring frequency: {str(e)}")
        return 'D'  # Default to daily on failure

@router.get("/files")
async def list_uploaded_files(current_user: str = Depends(get_current_user)):
    try:
        if not os.path.exists(UPLOAD_DIR):
            return {"status": "success", "files": []}
        
        files = os.listdir(UPLOAD_DIR)
        return {"status": "success", "files": files}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving file list: {str(e)}")

@router.get("/models")
async def get_all_models(current_user: str = Depends(get_current_user), conn = Depends(get_hana_connection)):
    try:       
        with conn.cursor() as cur:
            cur.execute("SELECT MODELNAME FROM DBADMIN.MODELS")
            models = [row[0] for row in cur.fetchall()]
        return {"models":models}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/run-forecast")
async def run_forecast(request: Request, current_user: str = Depends(get_current_user), conn = Depends(get_hana_connection)):
    try:
        data = await request.json()
        filename: Optional[str] = data.get("filename")
        granularity: str = data.get("granularity", "Overall")
        forecast_horizon: int = int(data.get("forecastHorizon", 30))
        time_bucket: str = data.get("timeBucket", "Daily")
        forecast_lock: int = int(data.get("forecastLock", 0))
        selected_models: List[str] = data.get("selectedModels", [])
        time_dependent_variables: List[str] = data.get("timeDependentVariables", [])
        column_mappings: Dict = data.get("columnMappings", {})
        holiday_config_data = data.get("holiday_config", {})
        best_fit_metric = data.get("bestFitMetric", "MAE")
        try:
            holiday_config = HolidayConfig(**holiday_config_data)
        
        except Exception as e:
            # Handle potential validation errors if UI sends bad data
            holiday_config = HolidayConfig()
            logging.warning(f"Could not get standard holidays: {holiday_config}. Error: {e}")
        
        if not filename:
            raise HTTPException(status_code=400, detail="Filename required")

        file_path = os.path.join(UPLOAD_DIR, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        try:
            result = run_forecast_for_file(
                conn,
                file_path,
                granularity,
                forecast_horizon,
                selected_models,
                time_dependent_variables,
                time_bucket,
                forecast_lock,
                column_mappings,
                holiday_config=holiday_config,
                best_fit_metric=best_fit_metric
            )

            serializable_result = make_json_serializable(result)
            try:
                json.dumps(serializable_result)  # test if serializable
                return JSONResponse(content=serializable_result, status_code=200)
            except TypeError as te:
                return JSONResponse(
                    status_code=200,
                    content={"status": "error", "message": f"Error serializing results: {str(te)}"}
                )

        except Exception as e:
            traceback_str = traceback.format_exc()
            return JSONResponse(
                status_code=200,
                content={
                    "status": "error",
                    "message": f"Error running forecast: {str(e)}",
                    "traceback": traceback_str
                }
            )

    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": f"Invalid JSON in request: {str(e)}"}
        )
    except Exception as e:
        traceback_str = traceback.format_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": f"Server error: {str(e)}", "traceback": traceback_str}
        )

# Function to map frontend granularity to backend forecast_type
def map_granularity_to_forecast_type(granularity):
    """Maps frontend granularity options to backend forecast_type values"""
    granularity_map = {
        "Overall": "Overall",
        "ProductID-wise": "Item-wise",
        "StoreID-ProductID Combination": "Store-Item Combination",
        # Add variations to handle potential truncation or misspellings
        "StoreID-ProductID Combinat": "Store-Item Combination",
        "StoreID-ProductID": "Store-Item Combination"
    }
    # Clean up the input granularity
    cleaned_granularity = granularity.strip() if isinstance(granularity, str) else granularity
    return granularity_map.get(cleaned_granularity, "Overall")

# Function to ensure dates are properly formatted
def ensure_date_format(df):
    """Ensure dates are in the correct format and properly set as datetime"""
    try:
        # Check if Date is already datetime
        if pd.api.types.is_datetime64_dtype(df['Date']):
            print("Date column is already in datetime format")
            return df
            
        # Convert to datetime with flexible parsing
        original_dates = df['Date'].copy()
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            
        if df['Date'].isna().any():
            # Try specific formats
            formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y']
            
            for fmt in formats:
                try:
                    test_dates = pd.to_datetime(original_dates, format=fmt, errors='coerce')
                    if test_dates.isna().sum() < df['Date'].isna().sum():
                        df['Date'] = test_dates
                        print(f"Converted dates using format {fmt}")
                        break
                except:
                    continue
            
        # Check if we still have NaT values and filter them out if necessary
        nat_count = df['Date'].isna().sum()
        if nat_count > 0:
            print(f"Warning: {nat_count} dates could not be parsed and will be removed")
            df = df.dropna(subset=['Date'])
            
        # Sort by date
        df = df.sort_values(by='Date')
        
        return df
    except Exception as e:
        print(f"Error in date formatting: {str(e)}")
        return df  # Return original DataFrame if we can't fix it
    
# Function to ensure required ID columns exist based on granularity
def ensure_id_columns_exist(df, forecast_type):
    """Ensure required ID columns exist based on the forecast type"""
    if forecast_type == "Item-wise" and "ProductID" not in df.columns:
        print("ProductID column missing, creating a default")
        df["ProductID"] = "default_product"
    
    if forecast_type == "Store-Item Combination":
        # Create default columns for StoreID and ProductID if needed
        if "StoreID" not in df.columns:
            print("StoreID column missing, creating default")
            df["StoreID"] = "default_store"
        if "ProductID" not in df.columns:
            print("ProductID column missing, creating default")
            df["ProductID"] = "default_product"
            
        # Create or update store_item column with consistent separator
        print("Creating/updating store_item column")
        df["store_item"] = df["StoreID"].astype(str).str.strip() + " - " + df["ProductID"].astype(str).str.strip()
        
        # Validate the store_item column
        if df["store_item"].isnull().any():
            print("Warning: Some store_item combinations contain null values")
            df["store_item"] = df["store_item"].fillna("unknown - unknown")
    
    return df

#Function to build the holiday df & features
def build_holidays_dataframe(holiday_config: HolidayConfig, all_dates: pd.Series) -> Optional[pd.DataFrame]:
    prophet_holidays = []
    
    if holiday_config.use_standard:
        try:
            years = all_dates.dt.year.unique()
            country_holidays = holidays.country_holidays(holiday_config.country, years=years)
            
            for date, name in country_holidays.items():
                prophet_holidays.append({'holiday': name, 'ds': pd.to_datetime(date)})
        except Exception as e:
            print(f"Warning: Could not get standard holidays for country: {holiday_config.country}. Error: {e}")

    for custom_event in holiday_config.custom:
        try:
            prophet_holidays.append({'holiday': custom_event.name, 'ds': pd.to_datetime(custom_event.date)})
        except Exception as e:
            print(f"Warning: Invalid custom holiday date format: {custom_event.date}. Error: {e}")

    if not prophet_holidays:
        return None
        
    return pd.DataFrame(prophet_holidays)

# Function to infer frequency
def infer_frequency(df, date_col='Date'):
    try:
        if date_col not in df.columns:
            print(f"'{date_col}' not found in DataFrame columns")
            return 'D'

        # Convert to datetime and get a Series of UNIQUE, SORTED dates
        unique_dates = pd.Series(pd.to_datetime(df[date_col], errors='coerce').dropna().unique()).sort_values()

        if len(unique_dates) < 2:
            # Not enough unique dates to infer, default to Daily
            return 'D'

        # Calculate differences between consecutive UNIQUE dates
        date_diffs = unique_dates.diff().dt.days.dropna()

        if date_diffs.empty:
            return 'D'

        most_common_diff = date_diffs.mode()[0]

        freq_map = {
            1: 'D', 7: 'W', 14: 'W', 28: 'M', 29: 'M', 30: 'M', 31: 'M',
            90: 'Q', 91: 'Q', 92: 'Q', 365: 'Y', 366: 'Y'
        }
        
        closest_diff = min(freq_map.keys(), key=lambda k: abs(k - most_common_diff))
        
        if abs(closest_diff - most_common_diff) <= 1:
            req = freq_map.get(closest_diff, 'D')
        else:
            freq = 'D'
        
        print(f"Inferred frequency: {freq} (most common diff: {most_common_diff} days)")
        return freq

    except Exception as e:
        print(f"Error inferring frequency: {str(e)}")
        return 'D'

# Function to detect seasonality
# In app/engine.py
def detect_seasonality(df, max_lags=50):   
    logging.info("### Seasonality Detection Started ")
    try:
        
        if 'Date' not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
            else:
                logging.warning("detect_seasonality requires a 'Date' column. Defaulting to period=7.")
                return 7

        inferred_freq = api_infer_frequency(df)
        logging.info(f"Data frequency for seasonality check: {inferred_freq}")

        freq_to_seasonality_map = {
            'D': 7,    # Daily data -> Weekly seasonality
            'W': 52,   # Weekly data -> Yearly seasonality
            'M': 12,   # Monthly data -> Yearly seasonality
            'Q': 4,    # Quarterly data -> Yearly seasonality
            'Y': 1     # Yearly data -> No seasonality
        }

        best_period = freq_to_seasonality_map.get(inferred_freq, 7)
        logging.info(f"### Seasonality Analysis Results: Based on frequency '{inferred_freq}', suggested period is {best_period}.")
        return best_period

    except Exception as e:
        logging.error(f"Error during fast seasonality detection: {e}. Defaulting to period=7.")
        return 7

def encode_categorical_columns(df, categorical_columns):
    try:
        df_encoded = df.copy()
        for col in categorical_columns:
            unique_categories = sorted(df_encoded[col].dropna().unique())
            df_encoded[col] = pd.Categorical(df_encoded[col], categories=unique_categories)
        return df_encoded
    except Exception as e:
        logging.error(f"Error encoding categorical columns: {e}")
        return df

# Function to calculate metrics
def calculate_metrics(y_true, y_pred):
    epsilon = 1e-6 # Prevents division by 0
    MAPE_CAP = 1000.0

    if y_true is None or y_pred is None:
        logging.warning("Invalid input: y_true or y_pred is None.")
        return None, None, None, None
    
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    if y_true.shape != y_pred.shape:
        logging.warning("Shape mismatch between y_true and y_pred.")
        return None, None, None, None

    if np.any(np.isnan(y_pred)) or np.any(np.isinf(y_pred)):
        logging.warning("Invalid predictions: NaN or Inf values detected.")
        return None, None, None, None

    try:
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        nonzero_idx = y_true > epsilon
        
        if np.any(nonzero_idx):
            individual_pe = np.abs((y_true[nonzero_idx] - y_pred[nonzero_idx]) / y_true[nonzero_idx]) * 100
            capped_pe = np.minimum(individual_pe, MAPE_CAP)
            mape = np.mean(capped_pe)
        else:               
            mape = 0.0 if np.sum(np.abs(y_pred)) == 0 else MAPE_CAP
            if np.isnan(mape):
                mape = None
                
        mae = mean_absolute_error(y_true, y_pred)
        bias = np.mean(y_pred - y_true)
        return rmse, mape, mae, bias
    
    except Exception as e:
        logging.error(f"Error calculating metrics: {e}")
        return None, None, None, None

# Function to auto-tune SARIMA
def auto_tune_sarima(demand_series, seasonal_period):
    model = auto_arima(
        demand_series,
        seasonal=True,
        m=seasonal_period,
        stepwise=True,
        suppress_warnings=True,
        error_action="ignore"
    )
    return model

def create_features(df, lags=3):
    try:
        df = df.copy()

        #creating lags
        for lag in range(1, lags+1):
            df[f'lag_{lag}'] = df['Demand'].shift(lag).astype(float)
        
        #Roll_Mean
        df['rolling_mean_3'] = df['Demand'].rolling(3).mean().astype(float)
        df['rolling_std_3'] = df['Demand'].rolling(3).std().astype(float)
        
        
        # Add date-based categorical features
        df['day_of_week'] = df.index.dayofweek
        df['month'] = df.index.month
        df['day_of_month'] = df.index.day

        logging.info(f"Final DataFrame Shape: {df.shape}")
        logging.info(f"Final DataFrame Columns: {df.columns}")

         # Drop rows with NaN values (introduced by lags and rolling stats)
        df = df.dropna()
        return df
    except Exception as e:
        logging.error(f"Feature creation error: {e}",exec_info = True)
        return None

def random_forest_model(train, val, test, horizon=30):
    try:
        logging.info("Starting Random Forest forecast")
        full_df = pd.concat([train, val, test])
        full_df = create_features(full_df)
 
        # One-hot encode categorical columns
        categorical_cols = full_df.select_dtypes(include=['category', 'object']).columns
        if not categorical_cols.empty:
            full_df = pd.get_dummies(full_df, columns=categorical_cols)

        # Split data
        train_len = len(train)
        val_len = len(val)
        
        X_train = full_df.iloc[:train_len].drop(columns=['Demand'])
        y_train = full_df.iloc[:train_len]['Demand']
        
        X_val = full_df.iloc[train_len:train_len+val_len].drop(columns=['Demand'])
        y_val = full_df.iloc[train_len:train_len+val_len]['Demand']
        
        X_test = full_df.iloc[train_len+val_len:].drop(columns=['Demand'])
        y_test = full_df.iloc[train_len+val_len:]['Demand']

        # Train model with enhanced parameters
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1  # Use all available cores
        )
        model.fit(X_train, y_train)
 
        # Prepare future dates
        freq = pd.infer_freq(test.index) or 'D'
        future_dates = pd.date_range(
            start=test.index[-1] + pd.Timedelta(days=1), 
            periods=horizon,  # Use horizon parameter instead of hardcoded 30
            freq=freq
        )

        # Initialize future dataframe with the same columns as X_train
        future_df = pd.DataFrame(index=future_dates, columns=X_train.columns)
        future_df = future_df.fillna(0)  # Fill with zeros initially
        predictions = []  # Store predictions here
 
        # Update time-based features for future dates
        for i, date in enumerate(future_dates):
            current_features = future_df.iloc[[i]].copy()
            
            if i >= 3:  # For lag features
                current_features['lag_1'] = predictions[i-1]
                current_features['lag_2'] = predictions[i-2]
                current_features['lag_3'] = predictions[i-3]
            else:  # Use last known values for initial predictions
                current_features['lag_1'] = X_test.iloc[-1]['lag_1']
                current_features['lag_2'] = X_test.iloc[-1]['lag_2']
                current_features['lag_3'] = X_test.iloc[-1]['lag_3']
            
            # Update time-based features
            if 'day_of_week' in X_train.columns:
                current_features['day_of_week'] = date.dayofweek
            if 'month' in X_train.columns:
                current_features['month'] = date.month
            if 'day_of_month' in X_train.columns:
                current_features['day_of_month'] = date.day
            if 'week_of_year' in X_train.columns:
                current_features['week_of_year'] = date.isocalendar()[1]
            if 'quarter' in X_train.columns:
                current_features['quarter'] = date.quarter
            
            # Make prediction
            pred = model.predict(current_features[X_train.columns])[0]
            predictions.append(pred)
            
            # Update future_df with the new features
            future_df.iloc[i] = current_features.iloc[0]
 
        # Calculate feature importances
        feature_importance = pd.DataFrame({
            'feature': X_train.columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        # Log feature importances
        logging.info("Random Forest Feature Importances:")
        logging.info(feature_importance)

        return {
            'train': calculate_metrics(y_train, model.predict(X_train)),
            'val': calculate_metrics(y_val, model.predict(X_val)),
            'test': calculate_metrics(y_test, model.predict(X_test)),
            'feature_importance': feature_importance
        }, predictions
    
    except Exception as e:
        logging.error(f"Random Forest Error: {str(e)}", exc_info=True)
        return f"Random Forest Failed: {str(e)}", None

def xgboost_model(train, val, test, horizon=30):
    try:
        logging.info("Starting XGBoost forecast")
        full_df = pd.concat([train, val, test])
        full_df = create_features(full_df)
 
        # One-hot encode categorical columns
        categorical_cols = full_df.select_dtypes(include=['category', 'object']).columns
        if not categorical_cols.empty:
            full_df = pd.get_dummies(full_df, columns=categorical_cols)

        # Split data
        train_len = len(train)
        val_len = len(val)
        
        X_train = full_df.iloc[:train_len].drop(columns=['Demand'])
        y_train = full_df.iloc[:train_len]['Demand']
        
        X_val = full_df.iloc[train_len:train_len+val_len].drop(columns=['Demand'])
        y_val = full_df.iloc[train_len:train_len+val_len]['Demand']
        
        X_test = full_df.iloc[train_len+val_len:].drop(columns=['Demand'])
        y_test = full_df.iloc[train_len+val_len:]['Demand']

        # Train model
        model = XGBRegressor(
            n_estimators=150,
            learning_rate=0.01,
            max_depth=8,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=0.1,
            early_stopping_rounds=20,
            eval_metric='mae'
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
 
        # Prepare future dates
        freq = pd.infer_freq(test.index) or 'D'
        future_dates = pd.date_range(
            start=test.index[-1] + pd.Timedelta(days=1), 
            periods=horizon,  # Use horizon parameter instead of hardcoded 30
            freq=freq
        )

        # Initialize future dataframe with the same columns as X_train
        future_df = pd.DataFrame(index=future_dates, columns=X_train.columns)
        future_df = future_df.fillna(0)  # Fill with zeros initially
        predictions = []  # Store predictions here
 
        # Update time-based features for future dates
        for i, date in enumerate(future_dates):
            current_features = future_df.iloc[[i]].copy()
            
            if i >= 3:  # For lag features
                current_features['lag_1'] = predictions[i-1]
                current_features['lag_2'] = predictions[i-2]
                current_features['lag_3'] = predictions[i-3]
            else:  # Use last known values for initial predictions
                current_features['lag_1'] = X_test.iloc[-1]['lag_1']
                current_features['lag_2'] = X_test.iloc[-1]['lag_2']
                current_features['lag_3'] = X_test.iloc[-1]['lag_3']
            
            # Update categorical features (one-hot encoded columns)
            if 'day_of_week' in X_train.columns:
                current_features['day_of_week'] = date.dayofweek
            if 'month' in X_train.columns:
                current_features['month'] = date.month
            if 'day_of_month' in X_train.columns:
                current_features['day_of_month'] = date.day
            
            # Make prediction
            pred = model.predict(current_features[model.feature_names_in_])[0]
            predictions.append(pred)
            
            # Update future_df with the new features
            future_df.iloc[i] = current_features.iloc[0]
 
        return {
            'train': calculate_metrics(y_train, model.predict(X_train)),
            'val': calculate_metrics(y_val, model.predict(X_val)),
            'test': calculate_metrics(y_test, model.predict(X_test))
        }, predictions
    
    except Exception as e:
        logging.error(f"XGBoost Error: {str(e)}", exc_info=True)
        return f"XGBoost Failed: {str(e)}", None

def lstm_model(train, val, test, n_steps=3, horizon=30):
    try:
        # Create sequences
        def create_sequences(data, n_steps):
            X, y = [], []
            for i in range(len(data)-n_steps):
                X.append(data[i:i+n_steps])
                y.append(data[i+n_steps])
            return np.array(X), np.array(y)
        
        # Scale data
        scaler = StandardScaler()
        train_scaled = scaler.fit_transform(train[['Demand']])
        val_scaled = scaler.transform(val[['Demand']])
        test_scaled = scaler.transform(test[['Demand']])
        
        # Create sequences
        X_train, y_train = create_sequences(train_scaled, n_steps)
        X_val, y_val = create_sequences(val_scaled, n_steps)
        X_test, y_test = create_sequences(test_scaled, n_steps)
        
        # Build model
        model = Sequential([
            LSTM(25, activation='relu', input_shape=(n_steps, 1)),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')
        
        # Train model
        early_stop = EarlyStopping(monitor='val_loss', patience=5)
        model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=15,
            batch_size=32,
            callbacks=[early_stop],
            verbose=0
        )
        
        # Generate forecasts
        future_forecast = []
        current_batch = test_scaled[-n_steps:]
        
        for _ in range(horizon):  # Use horizon parameter instead of hardcoded 30
            current_pred = model.predict(current_batch.reshape(1, n_steps, 1))[0][0]
            future_forecast.append(current_pred)
            current_batch = np.append(current_batch[1:], current_pred)
        
        return {
            'train': calculate_metrics(y_train, model.predict(X_train).flatten()),
            'val': calculate_metrics(y_val, model.predict(X_val).flatten()),
            'test': calculate_metrics(y_test, model.predict(X_test).flatten())
        }, scaler.inverse_transform(np.array(future_forecast).reshape(-1, 1)).flatten().tolist()
    except Exception as e:
        logging.error(f"LSTM Error: {str(e)}")
        return f"LSTM Failed: {str(e)}", None

def croston_model(train, val, test, alpha=0.4, method='classic', horizon=30): 
    try:
        full_df = pd.concat([train, val, test])
        demand = full_df['Demand'].astype(float).values
        train_len = len(train)
        val_len = len(val)
        
        demand_sizes = []
        inter_demand_intervals = []
        last_demand_idx = -1
        for i, d in enumerate(demand):
            if d > 0:
                demand_sizes.append(d)
                if last_demand_idx != -1:
                    inter_demand_intervals.append(i - last_demand_idx)
                last_demand_idx = i
        
        if not demand_sizes:
            return {'train': (0, 0, 0, 0), 'val': (0, 0, 0, 0), 'test': (0, 0, 0, 0)}, [0] * horizon  # Use horizon instead of 30
        
        z = demand_sizes[0]
        n = inter_demand_intervals[0] if inter_demand_intervals else 1
        z_smooth = [z]
        n_smooth = [n]
        forecasts = []
        
        for i in range(1, len(demand_sizes)):
            z = alpha * demand_sizes[i] + (1 - alpha) * z_smooth[-1]
            n = alpha * inter_demand_intervals[i-1] + (1 - alpha) * n_smooth[-1]
            z_smooth.append(z)
            n_smooth.append(n)
            forecast = z * (1 - alpha / 2) / n if method == 'sba' else z / n
            forecasts.append(forecast if n > 0 else 0)
        
        in_sample_forecast = np.zeros(len(demand))
        demand_idx = [i for i, d in enumerate(demand) if d > 0]
        for i, idx in enumerate(demand_idx[:-1]):
            forecast = z_smooth[i] * (1 - alpha / 2) / n_smooth[i] if method == 'sba' else z_smooth[i] / n_smooth[i]
            in_sample_forecast[idx] = forecast if n_smooth[i] > 0 else 0
        
        last_z = z_smooth[-1] if z_smooth else demand_sizes[-1]
        last_n = n_smooth[-1] if n_smooth else (inter_demand_intervals[-1] if inter_demand_intervals else 1)
        demand_var = np.var(demand_sizes) if len(demand_sizes) > 1 else 0
        
        future_forecast = []
        for _ in range(horizon):  # Replace 30 with horizon
            prob_demand = 1 / last_n
            if np.random.random() < prob_demand:
                demand_size = last_z + np.random.normal(0, np.sqrt(demand_var)) if demand_var > 0 else last_z
                demand_size = max(0, demand_size)
                forecast = demand_size * (1 - alpha / 2) / last_n if method == 'sba' else demand_size / last_n
                future_forecast.append(forecast)
            else:
                future_forecast.append(0)
        
        return {
            'train': calculate_metrics(demand[:train_len], in_sample_forecast[:train_len]),
            'val': calculate_metrics(demand[train_len:train_len + val_len], in_sample_forecast[train_len:train_len + val_len]),
            'test': calculate_metrics(demand[train_len + val_len:], in_sample_forecast[train_len + val_len:])
        }, future_forecast
    except Exception as e:
        logging.error(f"Croston Error: {str(e)}", exc_info=True)
        return f"Croston Failed: {str(e)}", None
    
def gru_model(train, val, test, n_steps=14, additional_cols=None, horizon=30):
    try:
        # Helper: Create single-step sequences
        def create_sequences(data, n_steps):
            X, y = [], []
            for i in range(len(data) - n_steps):
                X.append(data[i:i + n_steps])
                y.append(data[i + n_steps, 0])
            return np.array(X), np.array(y)

        # Features
        if additional_cols is None:
            additional_cols = []
        features = ['Demand'] + additional_cols

        # Scale the data
        scaler = StandardScaler()
        train_scaled = scaler.fit_transform(train[features])
        val_scaled = scaler.transform(val[features])
        test_scaled = scaler.transform(test[features])

        # Check data length
        if len(test_scaled) < n_steps:
            raise ValueError(f"Test data too short: {len(test_scaled)} rows, need at least {n_steps}")

        # Create sequences
        X_train, y_train = create_sequences(train_scaled, n_steps)
        X_val, y_val = create_sequences(val_scaled, n_steps)
        X_test, y_test = create_sequences(test_scaled, n_steps)

        # Validate sequence creation
        if X_train.size == 0 or y_train.size == 0:
            raise ValueError(f"No sequences created. Train rows: {len(train_scaled)}, n_steps: {n_steps}")

        # Print shapes
        print("X_train shape:", X_train.shape)
        print("y_train shape:", y_train.shape)
        print("X_val shape:", X_val.shape)
        print("y_val shape:", y_val.shape)
        print("X_test shape:", X_test.shape)
        print("y_test shape:", y_test.shape)

        # Build GRU model
        model = Sequential([
            GRU(32, activation='tanh', return_sequences=True, input_shape=(n_steps, len(features))),
            Dropout(0.2),
            GRU(16, activation='tanh'),
            Dense(1)
        ])

        # Compile
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.0005),
            loss='mse',
            run_eagerly=True
        )

        model.summary()

        # Callbacks
        early_stop = EarlyStopping(monitor='val_loss', patience=10)
        reduce_lr = ReduceLROnPlateau(monitor='val_loss', factor=0.2, patience=5, min_lr=0.0001)

        # Train
        history = model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=15,
            batch_size=32,
            callbacks=[early_stop, reduce_lr],
            verbose=1
        )

        # Test prediction
        sample_pred = model.predict(X_train[:1])
        print("Sample prediction shape:", sample_pred.shape)

        # Evaluate
        train_pred = model.predict(X_train).flatten()
        val_pred = model.predict(X_val).flatten()
        test_pred = model.predict(X_test).flatten()

        # Inverse transform predictions
        train_pred_full = np.zeros((len(train_pred), len(features)))
        val_pred_full = np.zeros((len(val_pred), len(features)))
        test_pred_full = np.zeros((len(test_pred), len(features)))
        train_pred_full[:, 0] = train_pred
        val_pred_full[:, 0] = val_pred
        test_pred_full[:, 0] = test_pred

        train_pred_inv = scaler.inverse_transform(train_pred_full)[:, 0]
        val_pred_inv = scaler.inverse_transform(val_pred_full)[:, 0]
        test_pred_inv = scaler.inverse_transform(test_pred_full)[:, 0]

        # Inverse transform ground truth
        y_train_full = np.zeros((len(y_train), len(features)))
        y_val_full = np.zeros((len(y_val), len(features)))
        y_test_full = np.zeros((len(y_test), len(features)))
        y_train_full[:, 0] = y_train
        y_val_full[:, 0] = y_val
        y_test_full[:, 0] = y_test

        y_train_inv = scaler.inverse_transform(y_train_full)[:, 0]
        y_val_inv = scaler.inverse_transform(y_val_full)[:, 0]
        y_test_inv = scaler.inverse_transform(y_test_full)[:, 0]

        # Compute metrics
        train_metrics = calculate_metrics(y_train_inv, train_pred_inv)
        val_metrics = calculate_metrics(y_val_inv, val_pred_inv)
        test_metrics = calculate_metrics(y_test_inv, test_pred_inv)

        # Future forecast (horizon steps instead of hardcoded 30)
        current_batch = test_scaled[-n_steps:]
        future_forecast = []
        for _ in range(horizon):  # Use horizon parameter instead of hardcoded 30
            pred = model.predict(current_batch.reshape(1, n_steps, len(features)), verbose=0)[0][0]
            future_forecast.append(pred)
            current_batch = np.roll(current_batch, -1, axis=0)
            current_batch[-1, 0] = pred

        future_full = np.zeros((horizon, len(features)))  # Use horizon instead of 30
        future_full[:, 0] = future_forecast
        future_forecast_inv = scaler.inverse_transform(future_full)[:, 0].tolist()

        metrics = {
            'train': train_metrics,
            'val': val_metrics,
            'test': test_metrics
        }
        return metrics, future_forecast_inv

    except Exception as e:
        logging.error(f"GRU Error: {str(e)}", exc_info=True)
        return f"GRU Failed: {str(e)}", None

def gaussian_process_model(train, val, test, horizon=30):
    try:
        logging.info("Starting Gaussian Process forecast")
        full_df = pd.concat([train, val, test])
        full_df = create_features(full_df)
 
        # One-hot encode categorical columns
        categorical_cols = full_df.select_dtypes(include=['category', 'object']).columns
        if not categorical_cols.empty:
            full_df = pd.get_dummies(full_df, columns=categorical_cols)

        # Split data
        train_len = len(train)
        val_len = len(val)
        
        X_train = full_df.iloc[:train_len].drop(columns=['Demand'])
        y_train = full_df.iloc[:train_len]['Demand']
        
        X_val = full_df.iloc[train_len:train_len+val_len].drop(columns=['Demand'])
        y_val = full_df.iloc[train_len:train_len+val_len]['Demand']
        
        X_test = full_df.iloc[train_len+val_len:].drop(columns=['Demand'])
        y_test = full_df.iloc[train_len+val_len:]['Demand']

        # Scale features and target with positive minimum bound
        scaler_X = StandardScaler()
        
        # Use custom scaler for target to ensure non-negative predictions
        y_min = y_train.min()
        y_max = y_train.max()
        y_range = y_max - y_min
        
        def scale_y(y):
            return (y - y_min) / y_range
        
        def inverse_scale_y(y_scaled):
            return y_scaled * y_range + y_min
        
        X_train_scaled = scaler_X.fit_transform(X_train)
        y_train_scaled = scale_y(y_train)
        
        X_val_scaled = scaler_X.transform(X_val)
        X_test_scaled = scaler_X.transform(X_test)

        # Define the kernel with appropriate length scales
        kernel = (
            ConstantKernel(1.0) * RBF(length_scale=1.0) +  # For smooth trends
            ExpSineSquared(length_scale=1.0, periodicity=1.0) +  # For periodic patterns
            WhiteKernel(noise_level=0.1)  # For noise
        )

        # Train model
        model = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=2,
            random_state=42,
            normalize_y=False  # We're handling normalization ourselves
        )
        model.fit(X_train_scaled, y_train_scaled)
 
        # Prepare future dates
        freq = pd.infer_freq(test.index) or 'D'
        future_dates = pd.date_range(
            start=test.index[-1] + pd.Timedelta(days=1), 
            periods=horizon,  # Use horizon parameter instead of hardcoded 30
            freq=freq
        )

        # Initialize future dataframe with the same columns as X_train
        future_df = pd.DataFrame(index=future_dates, columns=X_train.columns)
        future_df = future_df.fillna(0)  # Fill with zeros initially
        predictions = []  # Store predictions here
        uncertainties = []  # Store prediction uncertainties
 
        # Update time-based features for future dates
        for i, date in enumerate(future_dates):
            current_features = future_df.iloc[[i]].copy()
            
            if i >= 3:  # For lag features
                current_features['lag_1'] = predictions[i-1]
                current_features['lag_2'] = predictions[i-2]
                current_features['lag_3'] = predictions[i-3]
            else:  # Use last known values for initial predictions
                current_features['lag_1'] = X_test.iloc[-1]['lag_1']
                current_features['lag_2'] = X_test.iloc[-1]['lag_2']
                current_features['lag_3'] = X_test.iloc[-1]['lag_3']
            
            # Update time-based features
            if 'day_of_week' in X_train.columns:
                current_features['day_of_week'] = date.dayofweek
            if 'month' in X_train.columns:
                current_features['month'] = date.month
            if 'day_of_month' in X_train.columns:
                current_features['day_of_month'] = date.day
            if 'week_of_year' in X_train.columns:
                current_features['week_of_year'] = date.isocalendar()[1]
            if 'quarter' in X_train.columns:
                current_features['quarter'] = date.quarter
            
            # Scale features
            current_features_scaled = scaler_X.transform(current_features)
            
            # Make prediction with uncertainty
            pred_scaled, std = model.predict(current_features_scaled, return_std=True)
            
            # Inverse transform and ensure non-negative predictions
            pred = max(0, inverse_scale_y(pred_scaled[0]))  # Ensure non-negative
            uncertainty = std[0] * y_range  # Scale uncertainty back
            
            predictions.append(pred)
            uncertainties.append(uncertainty)
            
            # Update future_df with the new features
            future_df.iloc[i] = current_features.iloc[0]

        # Calculate metrics for training, validation, and test sets
        train_pred = np.maximum(0, inverse_scale_y(
            model.predict(scaler_X.transform(X_train))
        ))
        val_pred = np.maximum(0, inverse_scale_y(
            model.predict(scaler_X.transform(X_val))
        ))
        test_pred = np.maximum(0, inverse_scale_y(
            model.predict(scaler_X.transform(X_test))
        ))

        return {
            'train': calculate_metrics(y_train, train_pred),
            'val': calculate_metrics(y_val, val_pred),
            'test': calculate_metrics(y_test, test_pred),
            'uncertainties': uncertainties
        }, predictions
    
    except Exception as e:
        logging.error(f"Gaussian Process Error: {str(e)}", exc_info=True)
        return f"Gaussian Process Failed: {str(e)}", None

# Function to forecast using various models
def forecast_models(df, selected_models, additional_cols=None, item_col=None, forecast_type='Overall', horizon=30, holiday_config: HolidayConfig = None):
    # Create a copy of the dataframe to preserve the original
    df_copy = df.copy()
    
    if additional_cols is None:
        additional_cols = []
    
    # Store the dates before setting index
    dates = df_copy['Date'].copy()
    
    df_copy.set_index('Date', inplace=True)
    df_copy.sort_index(inplace=True)
    results = {}
    future_forecasts = {}
    skipped_items_log = [] 

    # Ensure 'Demand' column is of type float64
    df_copy['Demand'] = df_copy['Demand'].astype('float64')
    
    seasonal_period = None      
    seasonal_models = {'SARIMA', 'HWES'}
    
    if any(model in seasonal_models for model in selected_models):
        logging.info("A seasonal model was selected. Running seasonality detection...")
        try:
            seasonal_period = detect_seasonality(df_copy.reset_index())
        except Exception as e:
            logging.warning(f"Seasonality detection failed: {e}. Defaulting to period=7.")
            seasonal_period = 7
    else:
        logging.info("No seasonal models selected. Skipping seasonality detection.")
        
    holidays_df = None
    if holiday_config:
        # Note: Adjust frequency calculation if needed based on your time_bucket logic
        freq = pd.infer_freq(df_copy.index) or 'D'
        full_date_range_series = pd.Series(pd.date_range(start=df_copy.index.min(), end=df_copy.index.max() + pd.DateOffset(days=horizon), freq=freq))
        
        holidays_df = build_holidays_dataframe(holiday_config, full_date_range_series)
    

    # Split data into train, val, and test
    train_val, test = train_test_split(df_copy, test_size=0.2, shuffle=False)
    train, val = train_test_split(train_val, test_size=0.25, shuffle=False)

    # Identify categorical columns
    categorical_columns = df_copy.select_dtypes(include=['object']).columns.tolist()

    # Encode categorical columns
    train_encoded = encode_categorical_columns(train.reset_index(), categorical_columns)
    val_encoded = encode_categorical_columns(val.reset_index(), categorical_columns)
    test_encoded = encode_categorical_columns(test.reset_index(), categorical_columns)
    
    # If forecast_type is Item-wise or Store-Item Combination, we need to handle multiple items
    if forecast_type in ["Item-wise", "Store-Item Combination"] and item_col and item_col in df_copy.columns:
        unique_items = df_copy[item_col].unique()
        logging.info(f"Processing {len(unique_items)} unique items for {forecast_type} forecast")
        
        # Initialize future_forecasts with item structure
        for item in unique_items:
            future_forecasts[item] = {}
            item_df = df_copy[df_copy[item_col] == item].copy()
            
            try:
                if len(item_df) < 3:
                    raise ValueError("Not enough data points for a train/val/test split.")
                item_train_val, item_test = train_test_split(item_df, test_size=0.2, shuffle=False)
                item_train, item_val = train_test_split(item_train_val, test_size=0.25, shuffle=False)
                if item_train.empty or item_val.empty or item_test.empty:
                    raise ValueError("One of the data splits is empty.")
            
            except ValueError as e:
                log_message = f"Item '{item}': {len(item_df)} rows. {e}. Skipped."
                logging.warning(log_message)
                skipped_items_log.append(log_message)
                continue
            
            # Run forecasts for each model
            for model_name in selected_models:
                try:
                    if model_name == 'AR':
                        model = AutoReg(item_df['Demand'], lags=2).fit()
                        # Training performance
                        train_forecast = model.predict(start=0, end=len(item_train)-1)
                        train_rmse, train_mape, train_mae, train_bias = calculate_metrics(item_train['Demand'], train_forecast)
                        # Validation performance
                        val_forecast = model.predict(start=len(item_train), end=len(item_train) + len(item_val) - 1)
                        val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_val['Demand'], val_forecast)
                        # Test performance
                        test_forecast = model.predict(start=len(item_train) + len(item_val), end=len(item_train) + len(item_val) + len(item_test) - 1)
                        test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_test['Demand'], test_forecast)
                        
                        results[f"AR_{item}"] = {
                            'train': (train_rmse, train_mape, train_mae, train_bias),
                            'val': (val_rmse, val_mape, val_mae, val_bias),
                            'test': (test_rmse, test_mape, test_mae, test_bias)
                        }
                        
                        # future forecast 
                        final_model = AutoReg(item_df['Demand'], lags=2).fit()
                        future_forecast = final_model.predict(start=len(item_df), end=len(item_df) + horizon - 1)
                        future_forecasts[item]['AR'] = future_forecast.tolist()
                        
                    elif model_name == 'ARIMA':
                        try:
                            # Print shape and preview
                            print(f"[ARIMA] {item}: Demand len={len(item_df['Demand'])} (train={len(item_train)}, val={len(item_val)}, test={len(item_test)})")
                            # Fit on training data
                            model = ARIMA(item_train['Demand'], order=(2, 0, 1))
                            fitted_model = model.fit()
                            # Forecast for val+test
                            n_forecast = len(item_val) + len(item_test)
                            val_test_forecast = fitted_model.forecast(steps=n_forecast)
                            val_forecast = val_test_forecast[:len(item_val)]
                            test_forecast = val_test_forecast[len(item_val):]
                            # Metrics
                            train_rmse, train_mape, train_mae, train_bias = calculate_metrics(item_train['Demand'], fitted_model.fittedvalues)
                            val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_val['Demand'], val_forecast)
                            test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_test['Demand'], test_forecast)
                            results[f"ARIMA_{item}"] = {
                                'train': (train_rmse, train_mape, train_mae, train_bias),
                                'val': (val_rmse, val_mape, val_mae, val_bias),
                                'test': (test_rmse, test_mape, test_mae, test_bias)
                            }
                            # Fit final model for all data, forecast future
                            final_model = ARIMA(item_df['Demand'], order=(2, 0, 1)).fit()
                            future_forecast = final_model.forecast(steps=horizon)
                            print(f"[ARIMA] {item}: Forecasted {len(future_forecast)} steps. First 3: {future_forecast[:3].tolist()}")
                            future_forecasts[item]['ARIMA'] = future_forecast.tolist()
                        except Exception as e:
                            print(f"[ARIMA] {item} failed: {e}")
                            results[f"ARIMA_{item}"] = str(e)
                    
                    elif model_name == 'SARIMA':
                        #Train the model 
                        model = auto_tune_sarima(item_train['Demand'], seasonal_period)
                        
                        # Step 2: Calculate metrics correctly
                        train_rmse, train_mape, train_mae, train_bias = calculate_metrics(item_train['Demand'], model.predict_in_sample())                       
                        val_test_forecast = model.predict(n_periods=len(item_val) + len(item_test))
                        val_forecast = val_test_forecast[:len(item_val)]
                        test_forecast = val_test_forecast[len(item_val):]
                        val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_val['Demand'], val_forecast)
                        test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_test['Demand'], test_forecast)
                        
                        results[f"SARIMA_{item}"] = {
                            'train': (train_rmse, train_mape, train_mae, train_bias),
                            'val': (val_rmse, val_mape, val_mae, val_bias),
                            'test': (test_rmse, test_mape, test_mae, test_bias)
                        }
                        
                        #final future forecast 
                        final_model = auto_tune_sarima(item_df['Demand'], seasonal_period)
                        future_forecast = final_model.predict(n_periods=horizon)
                        future_forecasts[item]['SARIMA'] = future_forecast.tolist()
                    
                    elif model_name == 'VAR' and len(additional_cols) > 0:

                        df_train = item_train[['Demand'] + additional_cols]
                        df_val = item_val[['Demand'] + additional_cols]
                        df_test = item_test[['Demand'] + additional_cols]
                        df_train_diff = df_train.diff().dropna()

                        if len(df_train_diff) < 10:
                            logging.warning(f"Not enough data for VAR on item {item} after differencing. Skipping.")
                            continue
                        
                        model = VAR(df_train_diff)
                        model_fitted = model.fit(maxlags=5, ic='aic')
                        lag_order = model_fitted.k_ar
                        
                        train_pred_diff = model_fitted.predict(start=0, end=len(df_train_diff) - 1)
                        # Invert the predictions
                        train_pred = df_train.iloc[1:].copy() # Align indexes with differenced data
                        train_pred.iloc[lag_order:] = df_train.iloc[:-lag_order].values + train_pred_diff[lag_order:].cumsum()
                        train_rmse, train_mape, train_mae, train_bias = calculate_metrics(df_train['Demand'][lag_order+1:], train_pred['Demand'][lag_order+1:])

                        forecast_input = df_train_diff.values[-lag_order:]
                        future_pred_diff = model_fitted.forecast(y=forecast_input, steps=len(df_val) + len(df_test))
                        
                        df_future_pred_diff = pd.DataFrame(future_pred_diff, columns=df_train.columns)
                        last_train_actual = df_train.iloc[-1]
                        df_future_pred = df_future_pred_diff.cumsum() + last_train_actual

                        val_pred = df_future_pred.iloc[:len(df_val)]
                        test_pred = df_future_pred.iloc[len(df_val):]

                        val_rmse, val_mape, val_mae, val_bias = calculate_metrics(df_val['Demand'], val_pred['Demand'])
                        test_rmse, test_mape, test_mae, test_bias = calculate_metrics(df_test['Demand'], test_pred['Demand'])

                        results[f"VAR_{item}"] = {
                            'train': (train_rmse, train_mape, train_mae, train_bias),
                            'val': (val_rmse, val_mape, val_mae, val_bias),
                            'test': (test_rmse, test_mape, test_mae, test_bias)
                        }

                        final_future_forecast_diff = model_fitted.forecast(y=forecast_input, steps=horizon)
                        df_final_forecast_diff = pd.DataFrame(final_future_forecast_diff, columns=df_train.columns)
                        df_final_forecast = df_final_forecast_diff.cumsum() + last_train_actual
                        future_forecasts[item]['VAR'] = df_final_forecast['Demand'].tolist()
                        
                    elif model_name == 'VARMAX' and len(additional_cols) > 0:

                        varmax_df_train = item_train[['Demand'] + additional_cols]
                        model = VARMAX(varmax_df_train, order=(1, 1)).fit(disp=False)

                        train_pred = model.predict(start=0, end=len(varmax_df_train) - 1)
                        train_rmse, train_mape, train_mae, train_bias = calculate_metrics(item_train['Demand'], train_pred['Demand'])

                        future_pred = model.forecast(steps=len(item_val) + len(item_test))

                        val_pred = future_pred.iloc[:len(item_val)]
                        test_pred = future_pred.iloc[len(item_val):]

                        val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_val['Demand'], val_pred['Demand'])
                        test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_test['Demand'], test_pred['Demand'])

                        results[f"VARMAX_{item}"] = {
                            'train': (train_rmse, train_mape, train_mae, train_bias),
                            'val': (val_rmse, val_mape, val_mae, val_bias),
                            'test': (test_rmse, test_mape, test_mae, test_bias)
                        }

                        final_future_forecast = model.forecast(steps=horizon)
                        future_forecasts[item]['VARMAX'] = final_future_forecast['Demand'].tolist()
                    
                    elif model_name == 'SES':
                        freq = pd.infer_freq(item_train.index)
                        item_train_resampled = item_train.asfreq(freq)
                        model = SimpleExpSmoothing(item_train_resampled['Demand']).fit()
                        val_test_forecast = model.forecast(steps=len(item_val) + len(item_test))
                        val_forecast = val_test_forecast[:len(item_val)]
                        test_forecast = val_test_forecast[len(item_val):]
                        train_rmse, train_mape, train_mae, train_bias = calculate_metrics(item_train['Demand'], model.fittedvalues)
                        val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_val['Demand'], val_forecast)
                        test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_test['Demand'], test_forecast)

                        results[f"SES_{item}"] = {
                            'train': (train_rmse, train_mape, train_mae, train_bias),
                            'val': (val_rmse, val_mape, val_mae, val_bias),
                            'test': (test_rmse, test_mape, test_mae, test_bias)
                        }
                        
                        # Step 3: Generate the final future forecast by re-fitting on ALL historical data
                        final_model_train_data = item_df.asfreq(pd.infer_freq(item_df.index))
                        final_model = SimpleExpSmoothing(final_model_train_data['Demand']).fit()
                        future_forecast = final_model.forecast(steps=horizon)
                        future_forecasts[item]['SES'] = future_forecast.tolist()
                    
                    elif model_name == 'HSES':
                        try:
                            print(f"[HWES] {item}: Demand len={len(item_df['Demand'])}, train={len(item_train)}, val={len(item_val)}, test={len(item_test)}, seasonal_period={seasonal_period}")
                            
                            # Fit on train set
                            freq = pd.infer_freq(item_train.index) or 'D'
                            train_series = item_train['Demand'].asfreq(freq)
                            model = ExponentialSmoothing(
                                train_series,
                                seasonal='add',
                                seasonal_periods=seasonal_period
                            ).fit()
                            
                            # In-sample fit (train)
                            train_pred = model.fittedvalues
                            train_rmse, train_mape, train_mae, train_bias = calculate_metrics(train_series.values, train_pred.values)
                            
                            # Forecast val+test
                            n_valtest = len(item_val) + len(item_test)
                            valtest_forecast = model.forecast(steps=n_valtest)
                            val_forecast = valtest_forecast[:len(item_val)]
                            test_forecast = valtest_forecast[len(item_val):]
                            
                            val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_val['Demand'].values, val_forecast)
                            test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_test['Demand'].values, test_forecast)
                            
                            results[f"HWES_{item}"] = {
                                'train': (train_rmse, train_mape, train_mae, train_bias),
                                'val': (val_rmse, val_mape, val_mae, val_bias),
                                'test': (test_rmse, test_mape, test_mae, test_bias)
                            }
                            
                            # Final model on all data, for future
                            full_series = item_df['Demand'].asfreq(freq)
                            final_model = ExponentialSmoothing(
                                full_series,
                                seasonal='add',
                                seasonal_periods=seasonal_period
                            ).fit()
                            future_forecast = final_model.forecast(steps=horizon)
                            future_forecasts[item]['HWES'] = future_forecast.tolist()
                            print(f"[HWES] {item}: Successfully forecast {horizon} future steps")
                        except Exception as e:
                            print(f"[HWES] {item} failed: {e}")
                            results[f"HWES_{item}"] = str(e)
                    
                    elif model_name == 'Prophet':
                        try:
                            prophet_df = item_df.reset_index().rename(columns={'Date': 'ds', 'Demand': 'y'})
                            #initializing the model
                            model = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False,holidays=holidays_df)
                            #adding drivers
                            if additional_cols:
                                for driver in additional_cols:
                                    if driver in prophet_df.columns:
                                        logging.info(f"[Prophet] Adding regressor for item '{item}':'{driver}'")
                                        model.add_regressor(driver)
                                    else:
                                        logging.warning(f"[Prophet] Driver '{driver}' not found in data for item '{item}'. Skipping.")
                            #fitting the model
                            model.fit(prophet_df)
                            
                            # Training performance
                            train_forecast = model.predict(prophet_df)['yhat']
                            train_rmse, train_mape, train_mae, train_bias = calculate_metrics(item_df['Demand'].values, train_forecast)
                            # Validation performance
                            val_df = item_df.reset_index().rename(columns={'Date': 'ds'})
                            val_forecast = model.predict(val_df)['yhat']
                            val_rmse, val_mape, val_mae, val_bias = calculate_metrics(item_df['Demand'].values, val_forecast)
                            # Test performance
                            test_forecast = model.predict(item_df.reset_index().rename(columns={'Date': 'ds'}))['yhat']
                            test_rmse, test_mape, test_mae, test_bias = calculate_metrics(item_df['Demand'].values, test_forecast)
                            results[f"Prophet_{item}"] = {
                                'train': (train_rmse, train_mape, train_mae, train_bias),
                                'val': (val_rmse, val_mape, val_mae, val_bias),
                                'test': (test_rmse, test_mape, test_mae, test_bias)
                            }
                            # Future forecast
                            future = model.make_future_dataframe(periods=horizon)
                            
                            if additional_cols:
                                historical_drivers = prophet_df[['ds'] + additional_cols]
                                future = pd.merge(future, historical_drivers, on='ds', how='left')
                                future[additional_cols] = future[additional_cols].ffill()
                                future[additional_cols] = future[additional_cols].bfill()
                                future[additional_cols] = future[additional_cols].fillna(0)
                            
                            future_forecast = model.predict(future)['yhat'][-horizon:]
                            future_forecasts[item]['Prophet'] = future_forecast.tolist()
                        
                        except Exception as e:
                            logging.error(f"[Prophet] Model for item '{item}' failed: {e}", exc_info=True)
                            results[f"Prophet_{item}"] = str(e)
                    
                    elif model_name == 'XGBoost':
                        xgb_metrics, xgb_forecast = xgboost_model(item_train, item_val, item_test, horizon=horizon)
                        results[f"XGBoost_{item}"] = xgb_metrics
                        future_forecasts[item]['XGBoost'] = xgb_forecast
                    
                    elif model_name == 'Random Forest':
                        rf_metrics, rf_forecast = random_forest_model(item_train, item_val, item_test, horizon=horizon)
                        if isinstance(rf_metrics, dict):
                            results[f"Random Forest_{item}"] = rf_metrics
                            future_forecasts[item]['Random Forest'] = rf_forecast
                        else:
                            results[f"Random Forest_{item}"] = str(rf_metrics)
                    
                    elif model_name == 'LSTM':
                        lstm_metrics, lstm_forecast = lstm_model(item_train, item_val, item_test, horizon=horizon)
                        results[f"LSTM_{item}"] = lstm_metrics
                        future_forecasts[item]['LSTM'] = lstm_forecast
                    
                    elif model_name == 'Croston':
                        croston_metrics, croston_forecast = croston_model(item_train, item_val, item_test, alpha=0.4, horizon=horizon)
                        results[f"Croston_{item}"] = croston_metrics
                        future_forecasts[item]['Croston'] = croston_forecast
                    
                    elif model_name == 'GRU':
                        gru_metrics, gru_forecast = gru_model(item_train, item_val, item_test, horizon=horizon)
                        results[f"GRU_{item}"] = gru_metrics
                        future_forecasts[item]['GRU'] = gru_forecast
                    
                    elif model_name == 'Gaussian Process':
                        gp_metrics, gp_forecast = gaussian_process_model(item_train, item_val, item_test, horizon=horizon)
                        if isinstance(gp_metrics, dict):
                            results[f"Gaussian Process_{item}"] = gp_metrics
                            future_forecasts[item]['Gaussian Process'] = gp_forecast
                        else:
                            results[f"Gaussian Process_{item}"] = str(gp_metrics)
                except Exception as e:
                    logging.error(f"Error processing model {model_name} for item {item}: {e}")
                    results[f"{model_name}_{item}"] = str(e)
    else:
        # AR Model
        if 'AR' in selected_models:
            try:
                model = AutoReg(train['Demand'], lags=2).fit()
                val_forecast = model.predict(start=len(train), end=len(train) + len(val) - 1)
                test_forecast = model.predict(start=len(train) + len(val), end=len(train) + len(val) + len(test) - 1)
                results['AR'] = {
                    'train': calculate_metrics(train['Demand'], model.predict(start=0, end=len(train)-1)),
                    'val': calculate_metrics(val['Demand'], val_forecast),
                    'test': calculate_metrics(test['Demand'], test_forecast)
                }
                final_model = AutoReg(df_copy['Demand'], lags=2).fit()
                future_forecasts['AR'] = final_model.predict(start=len(df_copy), end=len(df_copy) + horizon - 1).tolist()
            except Exception as e:
                results['AR'] = str(e)

        # ARMA Model
        if 'ARMA' in selected_models:
            try:
                model = ARIMA(train['Demand'], order=(2, 0, 1)).fit()
                val_forecast = model.predict(start=len(train), end=len(train) + len(val) - 1)
                test_forecast = model.predict(start=len(train) + len(val), end=len(train) + len(val) + len(test) - 1)
                results['ARMA'] = {
                    'train': calculate_metrics(train['Demand'], model.predict(start=0, end=len(train)-1)),
                    'val': calculate_metrics(val['Demand'], val_forecast),
                    'test': calculate_metrics(test['Demand'], test_forecast)
                }
                final_model = ARIMA(df_copy['Demand'], order=(2, 0, 1)).fit()
                future_forecasts['ARMA'] = final_model.predict(start=len(df_copy), end=len(df_copy) + horizon - 1).tolist()
            except Exception as e:
                results['ARMA'] = str(e)

        # SARIMA Model
        if 'SARIMA' in selected_models:
            try:
                model = auto_tune_sarima(train['Demand'], seasonal_period)
                val_test_forecast = model.predict(n_periods=len(val) + len(test))
                results['SARIMA'] = {
                    'train': calculate_metrics(train['Demand'], model.predict_in_sample()),
                    'val': calculate_metrics(val['Demand'], val_test_forecast[:len(val)]),
                    'test': calculate_metrics(test['Demand'], val_test_forecast[len(val):])
                }
                final_model = auto_tune_sarima(df_copy['Demand'], seasonal_period)
                future_forecasts['SARIMA'] = final_model.predict(n_periods=horizon).tolist()
            except Exception as e:
                results['SARIMA'] = str(e)


        if 'VAR' in selected_models and len(additional_cols) > 0:
            try:
                # Prepare multivariate training data
                train_vars = df_copy[['Demand'] + [col + '_mapped' for col in additional_cols]]
                model = VAR(train_vars)
                model_fitted = model.fit()
            
                # Training performance
                train_forecast = model_fitted.forecast(train_vars.values[-model_fitted.k_ar:], steps=len(df_copy))
                train_rmse, train_mape, train_mae, train_bias = calculate_metrics(df_copy['Demand'].values, train_forecast[:, 0])

                # Validation performance
                val_forecast = model_fitted.forecast(train_vars.values[-model_fitted.k_ar:], steps=len(df_copy))
                val_rmse, val_mape, val_mae, val_bias = calculate_metrics(df_copy['Demand'].values, val_forecast[:, 0])
            
                # Test performance
                test_forecast = model_fitted.forecast(train_vars.values[-model_fitted.k_ar:], steps=len(df_copy))
                test_rmse, test_mape, test_mae, test_bias = calculate_metrics(df_copy['Demand'].values, test_forecast[:, 0])
            
                results['VAR'] = {
                    'train': (train_rmse, train_mape, train_mae, train_bias),
                    'val': (val_rmse, val_mape, val_mae, val_bias),
                    'test': (test_rmse, test_mape, test_mae, test_bias)
                }
            
                # Future forecast
                future_forecast = model_fitted.forecast(train_vars.values[-model_fitted.k_ar:], steps=horizon)
                future_forecasts['VAR'] = future_forecast[:, 0].tolist()
            except Exception as e:
                results['VAR'] = str(e)

        if 'VARMAX' in selected_models and len(additional_cols) > 0:
            try:
                # Prepare multivariate training data
                train_vars = train[['Demand'] + [col + '_mapped' for col in additional_cols]]
                model = VARMAX(train_vars, order=(1, 1)).fit(disp=False)
            
                # Training performance
                train_forecast = model.forecast(steps=len(df_copy))
                train_rmse, train_mape, train_mae, train_bias = calculate_metrics(df_copy['Demand'].values, train_forecast['Demand'])

                # Validation performance
                val_forecast = model.forecast(steps=len(df_copy))
                val_rmse, val_mape, val_mae, val_bias = calculate_metrics(df_copy['Demand'].values, val_forecast['Demand'])
            
                # Test performance
                test_forecast = model.forecast(steps=len(df_copy))
                test_rmse, test_mape, test_mae, test_bias = calculate_metrics(df_copy['Demand'].values, test_forecast['Demand'])
            
                results['VARMAX'] = {
                    'train': (train_rmse, train_mape, train_mae, train_bias),
                    'val': (val_rmse, val_mape, val_mae, val_bias),
                    'test': (test_rmse, test_mape, test_mae, test_bias)
                }
            
                # Future forecast
                future_forecast = model.forecast(steps=horizon)
                future_forecasts['VARMAX'] = future_forecast['Demand'].tolist()
            except Exception as e:
                results['VARMAX'] = str(e)

        # Simple Exponential Smoothing (SES)
        if 'SES' in selected_models:
            try:
                freq = pd.infer_freq(train.index)
                train_resampled = train.asfreq(freq) # Ensure frequency is set
                model = SimpleExpSmoothing(train_resampled['Demand']).fit()

                train_rmse, train_mape, train_mae, train_bias = calculate_metrics(train['Demand'], model.fittedvalues)

                val_test_forecast = model.forecast(steps=len(val) + len(test))
                val_forecast = val_test_forecast[:len(val)]
                test_forecast = val_test_forecast[len(val):]
                
                val_rmse, val_mape, val_mae, val_bias = calculate_metrics(val['Demand'], val_forecast)
                test_rmse, test_mape, test_mae, test_bias = calculate_metrics(test['Demand'], test_forecast)

                results['SES'] = {
                    'train': (train_rmse, train_mape, train_mae, train_bias),
                    'val': (val_rmse, val_mape, val_mae, val_bias),
                    'test': (test_rmse, test_mape, test_mae, test_bias)
                }
                
                final_model_train_data = df_copy.asfreq(pd.infer_freq(df_copy.index))
                final_model = SimpleExpSmoothing(final_model_train_data['Demand']).fit()
                future_forecast = final_model.forecast(steps=horizon)
                future_forecasts['SES'] = future_forecast.tolist()
            except Exception as e:
                logging.warning(f"SES model failed: {e}")
                results['SES'] = {'train': (0, 0, 0, 0), 'val': (float('inf'), 0, 0, 0), 'test': (0, 0, 0, 0)}
                future_forecasts['SES'] = [0] * horizon

        # Holt-Winters Exponential Smoothing (HWES)
        if 'HWES' in selected_models:
            try:
                freq = pd.infer_freq(train.index)
                train_resampled = train.asfreq(freq)
                model = ExponentialSmoothing(train_resampled['Demand'], seasonal='add', seasonal_periods=seasonal_period).fit()
                val_test_forecast = model.forecast(steps=len(val) + len(test))
                results['HWES'] = {
                    'train': calculate_metrics(train['Demand'], model.fittedvalues),
                    'val': calculate_metrics(val['Demand'], val_test_forecast[:len(val)]),
                    'test': calculate_metrics(test['Demand'], val_test_forecast[len(val):])
                }
                final_model_train_data = df_copy.asfreq(pd.infer_freq(df_copy.index))
                final_model = ExponentialSmoothing(final_model_train_data['Demand'], seasonal='add', seasonal_periods=seasonal_period).fit()
                future_forecasts['HWES'] = final_model.forecast(steps=horizon).tolist()
            except Exception as e:
                results['HWES'] = str(e)

        # Prophet Model
        if 'Prophet' in selected_models:
            try:
                prophet_df = df_copy.reset_index().rename(columns={'Date': 'ds', 'Demand': 'y'})               
                model = Prophet(
                    yearly_seasonality=True, 
                    weekly_seasonality=True, 
                    daily_seasonality=False, 
                    holidays=holidays_df
                )
                if additional_cols:
                    for driver in additional_cols:
                        if driver in prophet_df.columns:
                            logging.info(f"[Prophet] Adding regressor for Overall forecast: {driver}")
                            model.add_regressor(driver)
                        else:
                            logging.warning(f"[Prophet] Driver '{driver}' not found in data for Overall forecast. Skipping.")

                model.fit(prophet_df)

                # Training performance
                train_forecast = model.predict(prophet_df)['yhat']
                train_rmse, train_mape, train_mae, train_bias = calculate_metrics(df_copy['Demand'].values, train_forecast)
                # Validation performance
                val_df = df_copy.reset_index().rename(columns={'Date': 'ds'})
                val_forecast = model.predict(val_df)['yhat']
                val_rmse, val_mape, val_mae, val_bias = calculate_metrics(df_copy['Demand'].values, val_forecast)
                # Test performance
                test_forecast = model.predict(df_copy.reset_index().rename(columns={'Date': 'ds'}))['yhat']
                test_rmse, test_mape, test_mae, test_bias = calculate_metrics(df_copy['Demand'].values, test_forecast)
                results['Prophet'] = {
                    'train': (train_rmse, train_mape, train_mae, train_bias),
                    'val': (val_rmse, val_mape, val_mae, val_bias),
                    'test': (test_rmse, test_mape, test_mae, test_bias)
                }

                # Future forecast
                future = model.make_future_dataframe(periods=horizon)

                # FUTURE DATAFRAME WITH DRIVERS
                if additional_cols:
                    historical_drivers = prophet_df[['ds'] + additional_cols]
                    future = pd.merge(future, historical_drivers, on='ds', how='left')
                    future[additional_cols] = future[additional_cols].ffill()
                    future[additional_cols] = future[additional_cols].bfill()
                    future[additional_cols] = future[additional_cols].fillna(0)
                
                # This line now works because 'future' has the driver columns.
                future_forecast = model.predict(future)['yhat'][-horizon:]
                future_forecasts['Prophet'] = future_forecast.tolist()
                
            except Exception as e:
                # Add logging for errors
                logging.error(f"[Prophet] Overall forecast failed: {e}", exc_info=True)
                results['Prophet'] = str(e)
            

        # XGBoost
        if 'XGBoost' in selected_models:
            try:
                # Ensure proper data types
                train = train.copy()
                val = val.copy()
                test = test.copy()
                # Convert demand to float
                train['Demand'] = train['Demand'].astype(float)
                val['Demand'] = val['Demand'].astype(float)
                test['Demand'] = test['Demand'].astype(float)
                # Run XGBoost
                xgb_metrics, xgb_forecast = xgboost_model(train, val, test, horizon=horizon)
                results['XGBoost'] = xgb_metrics
                future_forecasts['XGBoost'] = xgb_forecast
            
            except Exception as e:
                results['XGBoost'] = str(e)

        # Random Forest
        if 'Random Forest' in selected_models:
            try:
                rf_metrics, rf_forecast = random_forest_model(train, val, test, horizon=horizon)
                if isinstance(rf_metrics, dict):
                    results['Random Forest'] = rf_metrics
                    future_forecasts['Random Forest'] = rf_forecast
                    
                    # Display feature importance if available
                    if 'feature_importance' in rf_metrics:
                        logging.info(f"Feature Importance: {rf_metrics['feature_importance']}")                       
                else:
                    results['Random Forest'] = str(rf_metrics)
            except Exception as e:
                results['Random Forest'] = str(e)

        #LSTM 
        if 'LSTM' in selected_models:
            try:
                lstm_metrics, lstm_forecast = lstm_model(item_train, item_val, item_test, horizon=horizon)
                results['LSTM'] = lstm_metrics
                future_forecasts['LSTM'] = lstm_forecast
            except Exception as e:
                results['LSTM'] = str(e)

        #Croston
        if 'Croston' in selected_models:
            croston_metrics, croston_forecast = croston_model(train, val, test, alpha=0.4,  horizon=horizon)  
            results['Croston'] = croston_metrics
            future_forecasts['Croston'] = croston_forecast

        #GRU
        if 'GRU' in selected_models:
            try:
                gru_metrics, gru_forecast = gru_model(train, val, test, horizon=horizon)
                results['GRU'] = gru_metrics
                future_forecasts['GRU'] = gru_forecast
            except Exception as e:
                results['GRU'] = str(e)


        # Gaussian Process
        if 'Gaussian Process' in selected_models:
            try:
                gp_metrics, gp_forecast = gaussian_process_model(train, val, test, horizon=horizon)
                if isinstance(gp_metrics, dict):
                    results['Gaussian Process'] = gp_metrics
                    future_forecasts['Gaussian Process'] = gp_forecast
                    
                    # Display uncertainties if available
                    if 'uncertainties' in gp_metrics:
                        # Calculate future dates for visualization
                        last_date = test.index[-1]
                        freq = pd.infer_freq(test.index) or 'D'
                        future_dates = pd.date_range(
                            start=last_date + pd.Timedelta(days=1),
                            periods=horizon,  # Use horizon instead of hardcoded 30
                            freq=freq
                        )
                        
                        
                        uncertainty_df = pd.DataFrame({
                            'Date': future_dates,
                            'Prediction': gp_forecast,
                            'Uncertainty': gp_metrics['uncertainties']
                        })
                        logging.info(f"Gaussian Process uncertainties:\n{uncertainty_df}")
                else:
                    results['Gaussian Process'] = str(gp_metrics)
            except Exception as e:
                results['Gaussian Process'] = str(e)
            

    return results, future_forecasts, dates, skipped_items_log

# Function to safely call forecast_models with proper date handling
def safe_forecast_models(df, selected_models, additional_cols=None, item_col=None, forecast_type='Overall', horizon=30, holiday_config: HolidayConfig = None):
    """A wrapper for forecast_models that ensures proper date handling"""
    try:
        # Check if Date is the index
        if isinstance(df.index, pd.DatetimeIndex) and 'Date' not in df.columns:
            # Reset index to get Date as a column
            df = df.reset_index()
            print("Reset DatetimeIndex to column 'Date'")
        
        # Make sure Date column exists and is not already an index
        if 'Date' in df.columns:
            # Convert to datetime if not already
            if not pd.api.types.is_datetime64_dtype(df['Date']):
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                df = df.dropna(subset=['Date'])
            
            # Now we're ready to call the original function
            # from .app import forecast_models

            # Later in your code
            results, future_forecasts, dates, skipped_items_log = forecast_models(df, selected_models, additional_cols, item_col, forecast_type, horizon, holiday_config=holiday_config)
            return results, future_forecasts, dates, skipped_items_log  # Explicitly return the result from forecast_models

        else:
            raise ValueError("DataFrame must have a 'Date' column or DatetimeIndex")
    
    except Exception as e:
        print(f"Error in safe_forecast_models: {str(e)}")
        traceback.print_exc()
        raise e
    
# Function to detect and adapt forecast data structure based on model
def adapt_forecast_structure(future_forecasts, forecast_type, selected_models=None, results=None, is_best_fit=False):
    """
    Adapts the forecast data structure to a standard format based on what's detected.
    Handles special cases like Prophet model results.
    
    Parameters:
    -----------
    future_forecasts : dict or list
        The future forecasts from the forecast_models function
    forecast_type : str
        The type of forecast: "Overall", "Item-wise", or "Store-Item Combination"
    selected_models : list, optional
        The models that were selected for forecasting
    results : dict, optional
        The results dictionary from forecast_models function
    is_best_fit : bool, optional
        Whether we're in Best Fit mode
        
    Returns:
    --------
    dict
        A standardized version of the future_forecasts dictionary
    """
    # If it's already empty or None, return a default structure
    if not future_forecasts:
        return {"Default": [0.0] * 30}  # Return a dummy forecast
    
    # Helper function to determine the most appropriate model name
    def get_model_name():
        if selected_models and len(selected_models) == 1:
            return selected_models[0]  # If only one model was selected, use that
        elif isinstance(results, dict) and "model_name" in results:
            return results["model_name"]
        elif selected_models and "Prophet" in selected_models:
            return "Prophet"  # Prefer Prophet if it was one of the selected models
        elif selected_models and len(selected_models) > 0:
            return selected_models[0]  # Use the first selected model
        else:
            return "Default"
            
    # If the top level is not a dict, wrap it
    if not isinstance(future_forecasts, dict):
        print(f"future_forecasts is not a dict, it's a {type(future_forecasts)}")
        # If it's a list, create a default model but try to infer the model name
        if isinstance(future_forecasts, list):
            model_name = get_model_name()
            return {model_name: future_forecasts}
        # If it's something else, return a default structure
        return {get_model_name(): [0.0] * 30}  # Return a dummy forecast
    
    # Create a copy to avoid modifying the original
    adapted_forecasts = {}
    
    # Get best fit models if in best fit mode
    best_fits = None
    if is_best_fit and results:
        best_fits = find_best_fit(results, forecast_type)
        print(f"Best fit models determined: {best_fits}")
    
    # Handle Prophet special case for Overall forecasts (single level)
    if forecast_type == "Overall":
        if is_best_fit and best_fits:
            best_model = best_fits.get("best_model")
            if best_model and best_model in future_forecasts:
                adapted_forecasts[best_model] = future_forecasts[best_model]
        else:
            for model_name, forecasts in future_forecasts.items():
                if isinstance(forecasts, dict):
                    adapted_forecasts[model_name] = {}
                    for sub_key, sub_forecasts in forecasts.items():
                        if not isinstance(sub_forecasts, list):
                            sub_forecasts = [float(sub_forecasts)]
                        adapted_forecasts[model_name][sub_key] = sub_forecasts
                else:
                    if not isinstance(forecasts, list):
                        forecasts = [float(forecasts)]
                    adapted_forecasts[model_name] = forecasts
                
    # Handle Prophet special case for Item-wise forecasts (two levels)
    elif forecast_type == "Item-wise":
        for item_id, item_forecasts in future_forecasts.items():
            adapted_forecasts[item_id] = {}
            if is_best_fit and best_fits and item_id in best_fits:
                best_model = best_fits[item_id].get("best_model")
                if best_model and isinstance(item_forecasts, dict) and best_model in item_forecasts:
                    adapted_forecasts[item_id][best_model] = item_forecasts[best_model]
            else:
                if isinstance(item_forecasts, dict):
                    for model_name, forecasts in item_forecasts.items():
                        if not isinstance(forecasts, list):
                            forecasts = [float(forecasts)]
                        adapted_forecasts[item_id][model_name] = forecasts
                else:
                    if not isinstance(item_forecasts, list):
                        item_forecasts = [float(item_forecasts)]
                    adapted_forecasts[item_id]["Default"] = item_forecasts
            
    # Handle Prophet special case for Store-Item Combination forecasts (two levels)
    elif forecast_type == "Store-Item Combination":
        for combo_id, combo_forecasts in future_forecasts.items():
            adapted_forecasts[combo_id] = {}
            if is_best_fit and best_fits and combo_id in best_fits:
                best_model = best_fits[combo_id].get("best_model")
                if best_model and isinstance(combo_forecasts, dict) and best_model in combo_forecasts:
                    adapted_forecasts[combo_id][best_model] = combo_forecasts[best_model]
            else:
                if isinstance(combo_forecasts, dict):
                    for model_name, forecasts in combo_forecasts.items():
                        if not isinstance(forecasts, list):
                            forecasts = [float(forecasts)]
                        adapted_forecasts[combo_id][model_name] = forecasts
                else:
                    if not isinstance(combo_forecasts, list):
                        combo_forecasts = [float(combo_forecasts)]
                    adapted_forecasts[combo_id]["Default"] = combo_forecasts
                
    return adapted_forecasts

# Function to transform forecast results into a CSV-ready format
def transform_forecasts_for_csv(results, future_forecasts, dates, forecast_type,run_type_label,future_dates=None, organization_id='default'):
    """Transform forecast results into CSV-ready format with organization-specific calendar support"""
    csv_rows = []
    
    # If future_dates are not provided, generate them based on forecast length
    if future_dates is None:
        try:
            # Detect frequency from the data
            freq = infer_frequency(pd.DataFrame({'Date': dates}))
            
            # Determine forecast length from future_forecasts
            forecast_length = 30  # default
            if isinstance(future_forecasts, dict) and len(future_forecasts) > 0:
                try:
                    first_item = next(iter(future_forecasts.values()))
                    if isinstance(first_item, dict) and len(first_item) > 0:
                        first_model = next(iter(first_item.values()))
                        if isinstance(first_model, list):
                            forecast_length = len(first_model)
                    elif isinstance(first_item, list):
                        forecast_length = len(first_item)
                except:
                    pass
            # Use current-date-based generation with organization calendar
            future_dates = generate_future_dates_from_current(forecast_length, freq, organization_id)
            future_dates = [date.strftime('%Y-%m-%d') for date in future_dates]
            
        except Exception as e:
            print(f"Error generating future dates: {e}")
            # Use actual forecast length if available, otherwise default to 30
            forecast_length = 30
            if isinstance(future_forecasts, dict) and len(future_forecasts) > 0:
                try:
                    first_item = next(iter(future_forecasts.values()))
                    if isinstance(first_item, dict) and len(first_item) > 0:
                        first_model = next(iter(first_item.values()))
                        if isinstance(first_model, list):
                            forecast_length = len(first_model)
                    elif isinstance(first_item, list):
                        forecast_length = len(first_item)
                except:
                    pass
            # Fallback to current-date-based daily generation with organization calendar
            future_dates = generate_future_dates_from_current(forecast_length, 'D', organization_id)
            future_dates = [date.strftime('%Y-%m-%d') for date in future_dates]

    # Case 1: Overall forecast
    if forecast_type == "Overall":
        for model_name, forecasts in future_forecasts.items():
            if isinstance(forecasts, dict) and hasattr(forecasts, 'items'):
                for inner_key, forecast_values in forecasts.items():
                    for i, forecast_value in enumerate(forecast_values):
                        if i < len(future_dates):
                            row = {
                                "Date": future_dates[i],
                                "Store": "",
                                "Item": inner_key,
                                "Model": model_name,
                                "Forecast": forecast_value,
                                "RunType": run_type_label 
                            }
                            csv_rows.append(row)
            else:
                for i, forecast_value in enumerate(forecasts):
                    if i < len(future_dates):
                        row = {
                            "Date": future_dates[i],
                            "Store": "",
                            "Item": "Total",
                            "Model": model_name,
                            "Forecast": forecast_value,
                            "RunType": run_type_label 
                        }
                        csv_rows.append(row)
    
    # Case 2: Item-wise forecast
    elif forecast_type == "Item-wise":
        for item_id, item_forecasts in future_forecasts.items():
            if isinstance(item_forecasts, dict) and hasattr(item_forecasts, 'items'):
                for model_name, forecasts in item_forecasts.items():
                    for i, forecast_value in enumerate(forecasts):
                        if i < len(future_dates):
                            item_name = str(item_id).strip() if item_id and str(item_id).strip() else "Unknown Item"
                            row = {
                                "Date": future_dates[i],
                                "Store": "",
                                "Item": item_name,
                                "Model": model_name,
                                "Forecast": forecast_value,
                                "RunType": run_type_label 
                            }
                            csv_rows.append(row)
            else:
                for i, forecast_value in enumerate(item_forecasts):
                    if i < len(future_dates):
                        item_name = str(item_id).strip() if item_id and str(item_id).strip() else "Unknown Item"
                        row = {
                            "Date": future_dates[i],
                            "Store": "",
                            "Item": item_name,
                            "Model": "Default",
                            "Forecast": forecast_value,
                            "RunType": run_type_label
                        }
                        csv_rows.append(row)
    
    # Case 3: Store-Item Combination forecast
    elif forecast_type == "Store-Item Combination":
        for combo_id, combo_forecasts in future_forecasts.items():
            # Split the combo ID using the consistent separator
            store_id = "Unknown Store"
            item_id = "Unknown Item"
            if isinstance(combo_id, str):
                parts = combo_id.split(" - ", 1)
                if len(parts) == 2:
                    store_id, item_id = parts
                    store_id = store_id.strip()
                    item_id = item_id.strip()
            
            if isinstance(combo_forecasts, dict) and hasattr(combo_forecasts, 'items'):
                for model_name, forecasts in combo_forecasts.items():
                    for i, forecast_value in enumerate(forecasts):
                        if i < len(future_dates):
                            row = {
                                "Date": future_dates[i],
                                "Store": store_id,
                                "Item": item_id,
                                "Model": model_name,
                                "Forecast": forecast_value,
                                "RunType": run_type_label
                            }
                            csv_rows.append(row)
            else:
                for i, forecast_value in enumerate(combo_forecasts):
                    if i < len(future_dates):
                        row = {
                            "Date": future_dates[i],
                            "Store": store_id,
                            "Item": item_id,
                            "Model": "Default",
                            "Forecast": forecast_value,
                            "RunType": run_type_label
                        }
                        csv_rows.append(row)
    
    return csv_rows

def attach_val_metrics_to_csv_rows(csv_data, results, forecast_type):
    for row in csv_data:
        # Use the same separator as in results keys!
        if forecast_type == "Overall":
            key = row['Model']
        elif forecast_type == "Item-wise":
            key = f"{row['Model']}_{row['Item']}"
        elif forecast_type == "Store-Item Combination":
            key = f"{row['Model']}_{row['Store']} - {row['Item']}"
        else:
            key = row['Model']

        val_metrics = results.get(key, {}).get('val', None)
        if val_metrics and isinstance(val_metrics, (list, tuple)) and len(val_metrics) == 4:
            row["RMSE"] = val_metrics[0]
            row["MAPE"] = val_metrics[1]
            row["MAE"]  = val_metrics[2]
            row["BIAS"] = val_metrics[3]
        else:
            # If metrics are missing, fill with None
            row["RMSE"] = None
            row["MAPE"] = None
            row["MAE"]  = None
            row["BIAS"] = None

    return csv_data

def upsert_full_forecast_run(conn, runid, historical_records, forecast_records, wipe_old=True):
    with conn.cursor() as cur:
        if wipe_old:
            cur.execute('DELETE FROM "DBADMIN"."FORECASTDATA" WHERE "FORECASTID" = ?', (runid,))
            print(f"Deleted any existing rows for FORECASTID={runid}")

        # Historical insert
        hist_values = [
            (
                runid,
                record.get("ProductID"),
                record.get("StoreID"),
                record.get("Date"),
                record.get("Demand"),
                runid
            )
            for record in historical_records
        ]
        if hist_values:
            cur.executemany(
                '''
                INSERT INTO "DBADMIN"."FORECASTDATA"
                ("FORECASTID", "PRODUCTID", "STOREID", "FORECASTDATE", "HISTORICALDEMAND", "RUNID")
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                hist_values
            )
            print(f"Inserted {len(hist_values)} historical records.")

        # Forecast insert
        fcst_values = [
            (
                runid,
                record.get("ProductID"),
                record.get("StoreID"),
                record.get("Date"),
                record.get("PredictedDemand"),
                record.get("MAPE"),
                record.get("RMSE"),
                record.get("BIAS"),
                record.get("MAE"),
                runid
            )
            for record in forecast_records
        ]
        if fcst_values:
            cur.executemany(
                '''
                INSERT INTO "DBADMIN"."FORECASTDATA"
                ("FORECASTID", "PRODUCTID", "STOREID", "FORECASTDATE",
                 "PREDICTEDDEMAND", "MAPE", "RMSE", "BIAS", "MAE","RUNID")
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,?)
                ''',
                fcst_values
            )
            print(f"Inserted {len(fcst_values)} forecast records.")

        conn.commit()
        print("Committed all inserts to FORECASTDATA.")

    return (len(hist_values), len(fcst_values))

def split_and_bulk_insert(conn, df_hist, df_forecast, forecast_id):
    # Map historical (only past/true Demand)
    historical_records = [
        {
            "ProductID": row.get("ProductID"),
            "StoreID": row.get("StoreID"),
            "Date": row.get("Date"),
            "Demand": row.get("Demand"),
        }
        for _, row in df_hist.iterrows()
    ]

    # Map forecast (from your csv_data)
    forecast_records = [
        {
            "ProductID": row.get("Item") or row.get("ProductID"),
            "StoreID": row.get("Store") or row.get("StoreID"),
            "Date": row.get("Date"),
            "PredictedDemand": row.get("Forecast"),
            "MAPE": row.get("MAPE"),   
            "RMSE": row.get("RMSE"),   
            "MAE": row.get("MAE"),     
            "BIAS": row.get("BIAS")
        }
        for _, row in df_forecast.iterrows()
    ]

    hist_count, fcst_count = upsert_full_forecast_run(
        conn,
        forecast_id,
        historical_records,
        forecast_records,
        wipe_old=True
    )
    print(f"Inserted {hist_count} historical rows and {fcst_count} forecast rows for forecast_id={forecast_id}")
    

def find_best_fit(results: dict, forecast_type: str, metric: str = "MAE"):
    """
    Finds the best fitting model based on a MAE on the validation set.
    """
    best_fit_summary = {}
    
    
    metric_map = {"RMSE": 0, "MAPE": 1, "MAE": 2, "BIAS": 3}
    metric_name = metric.upper()
    metric_index = metric_map.get(metric_name, 2)

    if forecast_type == "Overall":
        lowest_error = float('inf')
        best_model_name = "None"
        for model_name, metrics_data in results.items():
            if not isinstance(metrics_data, dict) or 'val' not in metrics_data or not metrics_data['val']:
                continue                  
            if metric_name == "BIAS":
                validation_score = abs(metrics_data['val'][metric_index])
            else:
                validation_score = metrics_data['val'][metric_index]

            if validation_score is not None and validation_score < lowest_error:
                lowest_error = validation_score
                best_model_name = model_name
            
            
        best_fit_summary = {
            "best_model": best_model_name,
            "metric": metric_name,
            "validation_score": lowest_error if lowest_error != float('inf') else None
        }
        
    else:
        best_fit_per_item = {}
        items = {}
        for key, metrics_data in results.items():
            if not isinstance(metrics_data, dict): continue
            try:
                model_name, item_id = key.rsplit('_', 1)
                if item_id not in items:
                    items[item_id] = {}
                items[item_id][model_name] = metrics_data
            except ValueError:
                logging.warning(f"Could not parse model/item from key: {key}")
                continue
        for item_id, item_models in items.items():
            lowest_error = float('inf')
            best_model_name = "None"
            for model_name, metrics_data in item_models.items():
                if 'val' not in metrics_data or not metrics_data['val']:
                    continue

                if metric_name == "BIAS":
                    validation_score = abs(metrics_data['val'][metric_index])
                else:
                    validation_score = metrics_data['val'][metric_index]

                if validation_score is not None and validation_score < lowest_error:
                    lowest_error = validation_score
                    best_model_name = model_name
                    
            best_fit_per_item[item_id] = {
                "best_model": best_model_name,
                "metric": metric_name,
                "validation_score": lowest_error if lowest_error != float('inf') else None
            }
        best_fit_summary = best_fit_per_item
    return best_fit_summary

# Running the forecast for the file -> 
def run_forecast_for_file(conn, file_path, granularity, forecast_horizon, selected_models, time_dependent_variables, time_bucket, forecast_lock, column_mappings, holiday_config: HolidayConfig,best_fit_metric: str = "MAE" ):
    """Run forecasting on a file using the specified parameters"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT MODELNAME FROM DBADMIN.MODELS")
            available_model_names = [row[0] for row in cur.fetchall()]
        
        if not selected_models:
            raise ValueError("No models were selected to run.")
        
        is_best_fit_mode = len(selected_models) > 1
        
        # Validate that all selected models are valid
        invalid_models = [model for model in selected_models if model not in available_model_names]
        if invalid_models:
            raise ValueError(f"Invalid model(s) selected: {invalid_models}. Available models are: {available_model_names}")

        if is_best_fit_mode:
            print(f"Best Fit mode: comparing models {selected_models} using metric '{best_fit_metric}'")
        else:
            print(f"Running single selected model: {selected_models[0]}")
        
        # Check if metadata file exists for this file
        metadata_path = os.path.join(UPLOAD_DIR, os.path.splitext(os.path.basename(file_path))[0] + "_metadata.json")
        metadata = {}
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                print(f"Loaded metadata from {metadata_path}")
                
                # If granularity was overridden in the request, note that
                if granularity != metadata.get("granularity"):
                    print(f"Granularity changed from {metadata.get('granularity')} to {granularity}")
                    
                # Update forecast_type if it's in the metadata
                stored_forecast_type = metadata.get("forecast_type")
                if stored_forecast_type:
                    forecast_type_from_granularity = map_granularity_to_forecast_type(granularity)
                    if stored_forecast_type != forecast_type_from_granularity:
                        print(f"Warning: Stored forecast_type ({stored_forecast_type}) differs from current granularity mapping ({forecast_type_from_granularity})")
                        print(f"Using new forecast_type: {forecast_type_from_granularity}")
                        
                # Get item_col from metadata if available
                item_col_from_metadata = metadata.get("item_col")
                if item_col_from_metadata:
                    print(f"Using item_col from metadata: {item_col_from_metadata}")
            except Exception as e:
                print(f"Error loading metadata: {e}")
        
        # Read the CSV file
        df = pd.read_csv(file_path, low_memory=False)
        print(f"Loaded DataFrame with columns: {df.columns.tolist()}")
        print(f"Using column mappings: {column_mappings}")
        print(f"--- [DEBUG] START: RUN FORECAST FOR FILE ---")
        print(f"--- [DEBUG] Initial DataFrame shape: {df.shape}")
        print(f"--- [DEBUG] User selected Time Bucket: {time_bucket}")

        
        # Get the mapped columns from column_mappings
        date_col = column_mappings.get("Date")
        demand_col = column_mappings.get("Demand")
        product_id_col = column_mappings.get("ProductID")
        store_id_col = column_mappings.get("StoreID")
        
        print(f"Looking for mapped Date column: {date_col}")
        print(f"Looking for mapped Demand column: {demand_col}")
        print(f"Looking for mapped ProductID column: {product_id_col}")
        print(f"Looking for mapped StoreID column: {store_id_col}")
        
        # Ensure all required columns exist and are named correctly
        # First, handle the Demand column
        if demand_col and demand_col in df.columns:
            print(f"Renaming '{demand_col}' to 'Demand'")
            # If Demand column already exists and is different from the mapped column, drop it
            if 'Demand' in df.columns and demand_col != 'Demand':
                print(f"Dropping existing 'Demand' column in favor of mapped column '{demand_col}'")
                df.drop('Demand', axis=1, inplace=True)
            df.rename(columns={demand_col: 'Demand'}, inplace=True)
        
        # Next, handle the Date column
        if date_col and date_col in df.columns:
            print(f"Renaming '{date_col}' to 'Date'")
            # If Date column already exists and is different from the mapped column, drop it
            if 'Date' in df.columns and date_col != 'Date':
                print(f"Dropping existing 'Date' column in favor of mapped column '{date_col}'")
                df.drop('Date', axis=1, inplace=True)
            df.rename(columns={date_col: 'Date'}, inplace=True)
        
        # Handle the ProductID column
        if product_id_col and product_id_col in df.columns:
            print(f"Renaming '{product_id_col}' to 'ProductID'")
            # If ProductID column already exists and is different from the mapped column, drop it
            if 'ProductID' in df.columns and product_id_col != 'ProductID':
                print(f"Dropping existing 'ProductID' column in favor of mapped column '{product_id_col}'")
                df.drop('ProductID', axis=1, inplace=True)
            df.rename(columns={product_id_col: 'ProductID'}, inplace=True)
        
        # Handle the StoreID column
        if store_id_col and store_id_col in df.columns:
            print(f"Renaming '{store_id_col}' to 'StoreID'")
            # If StoreID column already exists and is different from the mapped column, drop it
            if 'StoreID' in df.columns and store_id_col != 'StoreID':
                print(f"Dropping existing 'StoreID' column in favor of mapped column '{store_id_col}'")
                df.drop('StoreID', axis=1, inplace=True)
            df.rename(columns={store_id_col: 'StoreID'}, inplace=True)
        
        # Ensure Date column exists and is properly formatted
        if 'Date' not in df.columns:
            print("Date column missing, checking for mapped column")
            
            if date_col:
                print(f"Mapped Date column '{date_col}' was not found in the DataFrame")
                
            # Look for alternative date columns
            possible_date_cols = [col for col in df.columns if col.lower().find('date') >= 0 or 
                                col.lower().find('time') >= 0 or 
                                col.lower().find('day') >= 0 or 
                                col.lower().find('month') >= 0 or
                                col.lower().find('year') >= 0]
            
            if possible_date_cols:
                print(f"Found potential date columns: {possible_date_cols}")
                # Try to identify the most likely date column
                for col in possible_date_cols:
                    # Convert to string first to handle numeric date formats
                    test_series = df[col].astype(str)
                    # Try to convert to datetime
                    test_dates = pd.to_datetime(test_series, errors='coerce')
                    # If at least 90% of values are valid dates, use this column
                    if test_dates.notna().mean() >= 0.9:
                        print(f"Using '{col}' as the Date column (>90% valid dates)")
                        df.rename(columns={col: 'Date'}, inplace=True)
                        break
                else:
                    # If no column has >90% valid dates, use the first column in the list
                    print(f"Using '{possible_date_cols[0]}' as the Date column (best guess)")
                    df.rename(columns={possible_date_cols[0]: 'Date'}, inplace=True)
            else:
                raise ValueError("No Date column found in the DataFrame. Please map a date column to 'Date'.")
        
        print(f"Using column '{df.columns[df.columns == 'Date'][0]}' as the Date column")
        
        # Try to convert Date column to datetime with multiple formats
        date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y',
                        '%Y%m%d', '%d%m%Y', '%m%d%Y', '%b %d, %Y', '%B %d, %Y',
                        '%d %b %Y', '%d %B %Y', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S']
        
        # First try automatic conversion
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # If automatic conversion fails, try specific formats
        if df['Date'].isna().any():
            original_series = df['Date'].copy()
            for date_format in date_formats:
                try:
                    df['Date'] = pd.to_datetime(original_series, format=date_format, errors='coerce')
                    # If this format works for most values, use it
                    if df['Date'].notna().mean() > 0.9:
                        print(f"Successfully converted dates using format: {date_format}")
                        break
                except Exception:
                    continue
        
        # Check for NaT values after conversion
        if df['Date'].isna().any():
            print(f"Warning: Date column contains {df['Date'].isna().sum()} NaT values after conversion")
            # Remove rows with invalid dates
            orig_len = len(df)
            df = df.dropna(subset=['Date'])
            print(f"Removed {orig_len - len(df)} rows with invalid dates")
            
            if len(df) == 0:
                raise ValueError("No valid dates found after cleaning. Please check your date format.")
        
        # Sort by date
        df = df.sort_values(by='Date')
        
        # Ensure proper date formatting
        df = ensure_date_format(df)
        
        # Ensure Demand column exists
        if 'Demand' not in df.columns:
            print("Demand column missing, checking for mapped column")
            
            if demand_col:
                print(f"Mapped Demand column '{demand_col}' was not found in the DataFrame")
                
            # Look for potential numeric columns that might contain demand data
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            if numeric_cols:
                print(f"Found potential numeric columns for Demand: {numeric_cols}")
                # Rename the first numeric column to 'Demand'
                first_numeric = numeric_cols[0]
                print(f"Using '{first_numeric}' as the Demand column")
                df.rename(columns={first_numeric: 'Demand'}, inplace=True)
            else:
                raise ValueError("No suitable Demand column found in the DataFrame. Please map a numeric column to 'Demand'.")
                
        print(f"Using column '{df.columns[df.columns == 'Demand'][0]}' as the Demand column")
        
        # Convert Demand column to numeric
        df['Demand'] = pd.to_numeric(df['Demand'], errors='coerce')
        if df['Demand'].isna().sum() > 0:
            print(f"Warning: Demand column contains {df['Demand'].isna().sum()} NaN values after conversion")
            print("Applying imputation to fill missing values...")
            
            # Try interpolation first
            df_temp = df.copy()
            df_temp['Demand'] = df_temp['Demand'].interpolate(method='linear')
            
            # If there are still NaNs, use forward fill
            if df_temp['Demand'].isna().any():
                df_temp['Demand'] = df_temp['Demand'].fillna()
            
            # If there are still NaNs, use backward fill
            if df_temp['Demand'].isna().any():
                df_temp['Demand'] = df_temp['Demand'].fillna()
            
            # If there are still NaNs, fill with 0 as last resort
            if df_temp['Demand'].isna().any():
                df_temp['Demand'] = df_temp['Demand'].fillna(0)
                
            df = df_temp
            print(f"After imputation, NaN count: {df['Demand'].isna().sum()}")
        
        # Check for negative values in Demand
        neg_count = (df['Demand'] < 0).sum()
        if neg_count > 0:
            print(f"Warning: Demand column contains {neg_count} negative values")
        
        # Convert the granularity to forecast_type
        forecast_type = map_granularity_to_forecast_type(granularity)
        
        # Ensure required ID columns exist based on forecast type
        df = ensure_id_columns_exist(df, forecast_type)
        
        print(f"Running forecast with type: {forecast_type}, horizon: {forecast_horizon}, time bucket: {time_bucket}, forecast lock: {forecast_lock}")
        print(f"DataFrame shape: {df.shape}, date range: {df['Date'].min()} to {df['Date'].max()}")
        
        # Determine the appropriate item_col based on forecast_type
        item_col = None
        # First check if we have a valid item_col from metadata
        if 'item_col_from_metadata' in locals() and item_col_from_metadata and item_col_from_metadata in df.columns:
            print(f"Using item_col from metadata: {item_col_from_metadata}")
            item_col = item_col_from_metadata
        # Otherwise, determine based on forecast_type
        elif forecast_type == "Item-wise":
            if "ProductID" in df.columns:
                item_col = "ProductID"
                print(f"Using ProductID as item_col for Item-wise forecast")
            else:
                print(f"ProductID column not found, creating default")
                df["ProductID"] = "default_product"
                item_col = "ProductID"
        elif forecast_type == "Store-Item Combination":
            # Create a combined column for store-item if needed
            if "store_item" in df.columns:
                item_col = "store_item"
                print(f"Using existing store_item column")
            else:
                if "StoreID" in df.columns and "ProductID" in df.columns:
                    print(f"Creating store_item column from StoreID and ProductID")
                    df["store_item"] = df["StoreID"].astype(str) + "_" + df["ProductID"].astype(str)
                else:
                    print(f"StoreID or ProductID columns missing, creating default store_item")
                    df["store_item"] = "default_store_item"
                item_col = "store_item"
        
        detected_freq = api_infer_frequency(df, date_col='Date')
        print(f"Detected input data frequency: {detected_freq}")

        # Define frequency hierarchy and map user selection to a code
        freq_hierarchy = {'D': 1, 'W': 2, 'M': 3, 'Q': 4, 'Y': 5}
        freq_map = {'Daily': 'D', 'Weekly': 'W', 'Monthly': 'M', 'Quarterly': 'Q', 'Yearly': 'Y'}
        user_selected_freq_code = freq_map.get(time_bucket)

        detected_level = freq_hierarchy.get(detected_freq, 0)
        selected_level = freq_hierarchy.get(user_selected_freq_code, 0)

        # Apply logic rules
        if not selected_level:
            raise HTTPException(status_code=400, detail=f"Invalid time bucket selected: {time_bucket}")

        if detected_level < selected_level:
            print(f"Input data is finer-grained ('{detected_freq}'). Aggregating up to '{time_bucket}'...")
            df = aggregate_data(df, time_bucket, forecast_type, item_col, organization_id='default')
            print(f"Data successfully aggregated. New shape: {df.shape}")

        elif detected_level == selected_level:
            
            print(f"Input data frequency ('{detected_freq}') matches selection ('{time_bucket}'). Skipping aggregation.")
            

        else:          
            raise HTTPException(
                status_code=400,
                detail=f"Invalid request: Cannot forecast at a '{time_bucket}' frequency from data that is already aggregated as '{detected_freq}'. Please select a time bucket of '{detected_freq}' or coarser."
            )

        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df.dropna(subset=['Date'])  # Remove rows with invalid dates
            
            # Set Date as index for time series models
            df_indexed = df.set_index('Date').sort_index()
            
            # Check if we have enough data points
            if len(df_indexed) < 10:
                raise ValueError(f"Not enough valid data points after cleaning. Only {len(df_indexed)} rows remaining.")
            
            # Make a copy to prevent modification warnings
            df_for_forecast = df.set_index('Date').sort_index()
        else:
            raise ValueError("Date column is missing from the DataFrame after preprocessing.")
        
        # Run the forecast using the indexed DataFrame
        print(f"Running forecast models with DataFrame shape: {df_for_forecast.shape}")
        
        # Use our safe wrapper function to ensure proper date handling
        results, future_forecasts, dates, skipped_items_log = safe_forecast_models(
            df_for_forecast, 
            selected_models,
            additional_cols=time_dependent_variables,
            item_col=item_col,
            forecast_type=forecast_type,
            horizon=forecast_horizon,
            holiday_config=holiday_config
        )
        
        final_results = results
        final_forecasts = future_forecasts
        
        if is_best_fit_mode:
            best_fit_summary = find_best_fit(results, forecast_type, metric=best_fit_metric)
            logging.info(f"Best fit models determined: {best_fit_summary}")
            
            filtered_results = {}
            filtered_forecasts = {}
            
            if forecast_type == "Overall":
                best_model = best_fit_summary.get("best_model")
                if best_model and best_model in results:
                    filtered_results[best_model] = results[best_model]
                if best_model and best_model in future_forecasts:
                    filtered_forecasts[best_model] = future_forecasts[best_model]
            
            else: # For Item-wise or Store-Item Combination
                for item, summary in best_fit_summary.items():
                    best_model = summary.get("best_model")
                    if not best_model: continue                   
                    result_key = f"{best_model}_{item}"
                    if result_key in results:
                        filtered_results[result_key] = results[result_key]
                    
                    if item in future_forecasts and best_model in future_forecasts.get(item, {}):
                        filtered_forecasts[item] = {best_model: future_forecasts[item][best_model]}
            
            final_results = filtered_results
            final_forecasts = filtered_forecasts
        
        # Convert dates to serializable format if needed
        if isinstance(dates, pd.Series) or isinstance(dates, pd.DatetimeIndex):
            dates_list = dates.tolist()
        else:
            dates_list = dates
            
        # Make all results JSON-serializable
        response_data = {
            "status": "success",
            "results": make_json_serializable(final_results),
            "future_forecasts": adapt_forecast_structure(final_forecasts, forecast_type, selected_models, final_results, is_best_fit=is_best_fit_mode),
            "dates": make_json_serializable(dates_list),
            "forecast_type": forecast_type,  # Include the forecast type in the response
            "skipped_items": skipped_items_log,
            "config": {
                "granularity": granularity,
                "forecast_horizon": forecast_horizon,
                "time_bucket": time_bucket,
                "forecast_lock": forecast_lock,
                "selected_models": selected_models,
                "column_mappings": column_mappings
            }
        }
        
        print("Returning forecast response with keys:", list(response_data.keys()))
        print("Forecast type:", response_data.get('forecast_type'))
        
        run_type_label = "Best Fit" if is_best_fit_mode else "Manual Selection"
        
        #Forecasts for UI and db
        forecast_records =[]
        try:
            # --- GENERATE FUTURE DATES WITH THE CORRECT FREQUENCY --- #
            freq_map = {'Daily': 'D', 'Weekly': 'W', 'Monthly': 'M', 'Quarterly': 'Q', 'Yearly': 'Y'} 
            forecast_freq = freq_map.get(time_bucket, 'D') 
            print(f"Generating future dates with frequency: '{forecast_freq}' based on time bucket: '{time_bucket}'") 
            
            
            if dates_list:
                last_date = pd.to_datetime(dates_list[-1])
                future_dates_pd = pd.date_range(start=last_date, periods=forecast_horizon + 1, freq=forecast_freq)[1:]
                future_dates = [d.strftime('%Y-%m-%d') for d in future_dates_pd]
                
            else:
                future_dates_pd = pd.date_range(start=pd.Timestamp.now(), periods=forecast_horizon, freq=forecast_freq)
                future_dates = [d.strftime('%Y-%m-%d') for d in future_dates_pd] 
                
            
            # passing the run_type label, Transforms the forcast result into clean list of dictionary
            forecast_records = transform_forecasts_for_csv(
                results,
                response_data["future_forecasts"],
                dates_list,
                forecast_type,
                run_type_label,
                future_dates=future_dates
            )
            
            forecast_records = attach_val_metrics_to_csv_rows(forecast_records, results, forecast_type)
            
            response_data["csv_data"] = forecast_records
            print(f"Successfully prepared {len(forecast_records)} forecast records")
            
        except Exception as e:
            print(f"Error preparing forecast records for DB/UI: {str(e)}")
            traceback.print_exc()
            response_data["csv_data"] = []
            
        
        if forecast_records:
            try:
                with conn.cursor() as cur:
                    forecast_json_blob = json.dumps(make_json_serializable(forecast_records))
                    cur.execute(
                        'INSERT INTO "DBADMIN"."FINAL_FORECASTS" ("FORECASTDATA") VALUES (?)', (forecast_json_blob,)
                    )
                    
                    cur.execute(
                        'SELECT CURRENT_IDENTITY_VALUE() FROM "DBADMIN"."FINAL_FORECASTS"')
                    forecast_id = cur.fetchone()[0]
                    conn.commit()
                    response_data["forecast_id"] = forecast_id
                    print(f"Successfully inserted forecast run with ID: {forecast_id}")
                
                try:
                    # Prepare the DataFrames
                    df_hist = df[["ProductID", "StoreID", "Date", "Demand"]].dropna(subset=["Demand"])
                    df_forecast = pd.DataFrame(forecast_records)
                    split_and_bulk_insert(conn, df_hist, df_forecast, forecast_id)
                
                except Exception as split_bulk_e:
                    print(f"Error in split_and_bulk_insert: {split_bulk_e}")
                    traceback.print_exc()
                    response_data["db_error"] = f"Row-level insert failed: {split_bulk_e}"


            except Exception as db_e:
                print(f"Database insertion into FINAL_FORECASTS failed: {str(db_e)}")
                traceback.print_exc()
                response_data["db_error"] = f"Failed to save to database: {str(db_e)}"
                    
        return response_data
        
    except Exception as e:
        print(f"Error in run_forecast_for_file: {str(e)}")
        traceback.print_exc()
        raise e


def make_json_serializable(obj):
    """Convert pandas Timestamps, numpy types and other non-serializable objects to serializable types"""
    if isinstance(obj, dict):
        return {str(k): make_json_serializable(v) for k, v in obj.items()}  # Convert all keys to strings
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(make_json_serializable(item) for item in obj)
    elif isinstance(obj, pd.Timestamp):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(obj, pd.DatetimeIndex):
        return [d.strftime('%Y-%m-%d %H:%M:%S') for d in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.int_, np.intc, np.intp, np.int8, np.int16, np.int32, np.int64,
                        np.uint8, np.uint16, np.uint32, np.uint64)):
        return int(obj)
    elif isinstance(obj, (np.float_, np.float16, np.float32, np.float64)):
        return float(obj)

    elif isinstance(obj, pd.Series):
        return make_json_serializable(obj.tolist())
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    else:
        try:
            # Try to convert to string if it's not a basic type
            return str(obj)
        except:
            return None
    
@router.get("/download/{file_name}")
async def download_file(file_name: str, current_user: str = Depends(get_current_user)):
    print(file_name)
    try:
        file_path = os.path.join(UPLOAD_DIR, file_name)

        if not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(path=file_path, filename=file_name, media_type='application/octet-stream')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

@router.get("/forecastdata")
async def get_forecasted_date(current_user: str = Depends(get_current_user), conn = Depends(get_hana_connection)):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM DBADMIN.FINAL_FORECASTS")
            result = cur.fetchall()

        forecasts = [dict(zip([column[0] for column in cur.description], row)) for row in result]
        return {"status": "success", "forecasts": forecasts}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving forecast data: {str(e)}") 

@router.post("/login")
async def login(request: LoginRequest, conn=Depends(get_hana_connection)):
    try:
        with conn.cursor() as cur:
            query = "SELECT PASSWORDHASH FROM DBADMIN.USERS WHERE username = ?"
            cur.execute(query, (request.username,))
            result = cur.fetchone()
            # print(result[0])
        if not result:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        hashed_password = result[0]
        if hashed_password != request.password:
            raise HTTPException(status_code=401, detail="Invalid username or password")
        # if not verify_password(request.password, hashed_password):
        #     raise HTTPException(status_code=401, detail="Invalid username or password")

        # Generate JWT token using the utility function
        access_token = create_access_token(sub=request.username)

        return {"access_token": access_token, "token_type": "bearer", "status": "success"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")
    
@router.post("/uploadfile")
async def upload_file(file: UploadFile = File(...),current_user: str = Depends(get_current_user)):
    try:
        # Ensure the upload directory exists
        if not os.path.exists(UPLOAD_DIR):
            os.makedirs(UPLOAD_DIR)

        # Construct the file path
        file_path = os.path.join(UPLOAD_DIR, file.filename)

        # Save the uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "status": "success",
            "message": f"File '{file.filename}' has been uploaded.",
            "file_path": file_path
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")
    

@router.post("/deletefile")
async def delete_file(request: DeleteFileRequest, current_user: str = Depends(get_current_user)):
    try:
        # Construct the file path
        file_path = os.path.join(UPLOAD_DIR, request.filename)

        # Check if the file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File '{request.filename}' not found")

        # Delete the file
        os.remove(file_path)

        return {
            "status": "success",
            "message": f"File '{request.filename}' has been deleted."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

@router.post("/forecastinput")
async def forecast_input(request: ForecastInput, current_user: str = Depends(get_current_user)):
    try:
        # Ensure the upload directory exists
        if not os.path.exists(UPLOAD_DIR):
            os.makedirs(UPLOAD_DIR)

        # Construct the file path
        file_path = os.path.join(UPLOAD_DIR, f"{request.filename}.json")

        # Save the forecast data to a file
        with open(file_path, "w") as file:
            json.dump(request.data, file)
        
        return {
            "status": "success",
            "message": f"Forecast data saved as {request.filename}.json",
            "file_path": file_path
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving forecast input: {str(e)}")

def upload_to_staging_table(conn, data_dict):
    try:
        print("Entering upload_to_staging_table")

        data_json = json.dumps(data_dict)  
        with conn.cursor() as cur:
            print("About to insert to DB")
            insert_sql = '''
                INSERT INTO "DBADMIN"."HISTORICALDATA_STAGE" ("DATA_JSON")
                VALUES (?)
            '''
            cur.execute(insert_sql, (data_json))
            conn.commit()
            print("Insert committed to DB")
            
            # Get the auto-generated RUNID        
            cur.execute('SELECT CURRENT_IDENTITY_VALUE() FROM "DBADMIN"."HISTORICALDATA_STAGE"')
            new_runid = cur.fetchone()[0]
        print(f"Returning new_runid: {new_runid}")
        
        return new_runid
    except Exception as e:
        print(f"Exception in upload_to_staging_table: {e}")
    
@router.post("/upload-cleaned-data-json")
async def upload_clean_date(request: UploadCleanedData, current_user: str = Depends(get_current_user)):
    try:
        # Ensure the upload directory exists
        if not os.path.exists(UPLOAD_DIR):
            os.makedirs(UPLOAD_DIR)

        file_path = os.path.join(UPLOAD_DIR, f"{request.filename}.json")

        # Prepare the data to save
        cleaned_data = {
            "granularity": request.granularity,
            "timeBucket": request.timeBucket,
            "forecastHorizon": request.forecastHorizon,
            "data": request.data
        }

        # Save the cleaned data as a JSON file
        with open(file_path, "w") as file:
            json.dump(cleaned_data, file)    
        return {
            "status": "success",
            "message": f"Cleaned data saved as {request.filename}.json ",
            "file_path": file_path
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving cleaned data: {str(e)}")

@router.get("/download/{filename}")
async def download_file(
    filename: str, 
    current_user: str = Depends(get_current_user)  # Protect the endpoint
):
    try:
        # Decode any URL-encoded parts of the filename
        decoded_filename = unquote(filename)

        # Construct the full file path
        file_path = os.path.join(UPLOAD_DIR, decoded_filename)

        # Check if the file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File '{decoded_filename}' not found")

        # Return the file as a response
        return FileResponse(
            path=file_path,
            media_type="application/octet-stream",
            filename=decoded_filename
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

@router.get("/dashboard-data")
async def get_dashboard_data(
    current_user: str = Depends(get_current_user),
    conn=Depends(get_hana_connection),
    product: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    store: Optional[str] = Query(None)
):
    with conn.cursor() as cur:
        # Get latest FORECASTID
        cur.execute("SELECT MAX(FORECASTID) FROM DBADMIN.FORECASTDATA")
        row = cur.fetchone()
        latest_forecastid = row[0] if row and row[0] is not None else 1

        # 1. Get all distinct filter values (latest run only)
        cur.execute("SELECT DISTINCT PRODUCTID FROM DBADMIN.FORECASTDATA WHERE FORECASTID = ?", (latest_forecastid,))
        product_list = [row[0] for row in cur.fetchall()] or []
        cur.execute("SELECT DISTINCT STOREID FROM DBADMIN.FORECASTDATA WHERE FORECASTID = ?", (latest_forecastid,))
        store_list = [row[0] for row in cur.fetchall()] or []
        cur.execute("SELECT MODELNAME FROM DBADMIN.MODELS")
        model_list = [row[0] for row in cur.fetchall()] or []

        # Min/max dates for date pickers
        cur.execute("""
            SELECT MIN(FORECASTDATE), MAX(FORECASTDATE)
            FROM DBADMIN.FORECASTDATA
            WHERE FORECASTID = ? 
            AND PREDICTEDDEMAND IS NOT NULL OR HISTORICALDEMAND IS NOT NULL
        """, (latest_forecastid,))
        row = cur.fetchone()
        min_date = str(row[0]) if row and row[0] else ""
        max_date = str(row[1]) if row and row[1] else ""

        # --- Apply filters ---
        where_clauses = ["FORECASTID = ?"]
        params = [latest_forecastid]
        if product and product != "All":
            where_clauses.append("PRODUCTID = ?")
            params.append(product)
        if store and store != "All":
            where_clauses.append("STOREID = ?")
            params.append(store)
        if start:
            where_clauses.append("FORECASTDATE >= ?")
            params.append(str(start))
        if end:
            where_clauses.append("FORECASTDATE <= ?")
            params.append(str(end))
        where_str = " AND ".join(where_clauses)

        # 2. KPIs
        cur.execute(f"""
            SELECT
                COALESCE(SUM(PREDICTEDDEMAND), 0),
                AVG(MAPE),
                AVG(MAE),
                AVG(BIAS),
                COALESCE(SUM(MAPE * PREDICTEDDEMAND) / NULLIF(SUM(PREDICTEDDEMAND), 0), 0)
            FROM DBADMIN.FORECASTDATA
            WHERE {where_str}
              AND PREDICTEDDEMAND IS NOT NULL
        """, params)
        row = cur.fetchone() or [0, 0, 0, 0, 0]
        kpiData = {
            "total_demand": float(row[0] or 0),
            "mape": float(row[1] or 0),
            "mae": float(row[2] or 0),
            "forecast_bias": float(row[3] or 0),
            "weighted_mape": float(row[4] or 0),
        }

        # 3. Timeseries chart data
        cur.execute(f"""
            SELECT FORECASTDATE, MAX(HISTORICALDEMAND) AS actual, MAX(PREDICTEDDEMAND) AS forecast
            FROM DBADMIN.FORECASTDATA
            WHERE {where_str}
            GROUP BY FORECASTDATE
            ORDER BY FORECASTDATE
        """, params)
        timeseries = [
            {
                "date": str(r[0]),
                "actual": float(r[1]) if r[1] is not None else None,
                "forecast": float(r[2]) if r[2] is not None else None
            }
            for r in cur.fetchall()
        ]
        
        product_sales_breakdown =[]
        if store and store not in ["All", "All Stores"]:
            where_clauses = ["FORECASTID = ?", "STOREID = ?"]
            params = [latest_forecastid, store]
            if start:
                where_clauses.append("FORECASTDATE >= ?")
                params.append(str(start))
            if end:
                where_clauses.append("FORECASTDATE <= ?")
                params.append(str(end))
            where_str = " AND ".join(where_clauses)
            cur.execute(f"""
                SELECT PRODUCTID,
                       COALESCE(SUM(HISTORICALDEMAND), 0) AS sales,
                       COALESCE(SUM(PREDICTEDDEMAND), 0) AS forecast
                FROM DBADMIN.FORECASTDATA
                WHERE {where_str}
                GROUP BY PRODUCTID
                ORDER BY PRODUCTID
            """, params)
            product_sales_breakdown = [
                {
                    "product":row[0],
                    "sales":float(row[1]),
                    "forecast":float(row[2])
                }
                for row in cur.fetchall()
            ]
            
        # 4. Fetch and Process Data for Accuracy Charts
        accuracy_where_clauses = ["p.FORECASTID = ?"]
        accuracy_params = [latest_forecastid]

        if product and product not in ["All", "All Products"]:
            accuracy_where_clauses.append("p.PRODUCTID = ?")
            accuracy_params.append(product)
        if store and store not in ["All", "All Stores"]:
            accuracy_where_clauses.append("p.STOREID = ?")
            accuracy_params.append(store)
        if start:
            accuracy_where_clauses.append("p.FORECASTDATE >= ?")
            accuracy_params.append(str(start))
        if end:
            accuracy_where_clauses.append("p.FORECASTDATE <= ?")
            accuracy_params.append(str(end))

        accuracy_where_str = " AND ".join(accuracy_where_clauses)

        accuracy_query = f"""
        WITH Predictions AS (
            SELECT FORECASTDATE, PRODUCTID, STOREID, PREDICTEDDEMAND
            FROM FORECASTDATA p
            WHERE {accuracy_where_str}
        )
        SELECT
            p.PRODUCTID as product, p.STOREID as store,
            p.FORECASTDATE as "date", p.PREDICTEDDEMAND as forecast,
            a.ACTUAL_UNITS as actual
        FROM Predictions p
        JOIN ACTUALS_DATA a ON p.PRODUCTID = a.PRODUCTID AND p.STOREID = a.STOREID AND p.FORECASTDATE = a.SALESDATE
        """

        cur.execute(accuracy_query, accuracy_params)
        columns = [desc[0].lower() for desc in cur.description]
        accuracy_data = [dict(zip(columns, row)) for row in cur.fetchall()]

        # Process this new data for our two charts
        forecast_variance = {}
        drilldown_data = {}

        for row in accuracy_data:
            prod, stor, actual_val, forecast_val, date_str = row['product'], row['store'] or 'N/A', float(row['actual']), float(row['forecast']), str(row['date'])
            
            # Aggregate for Waterfall Chart
            forecast_variance.setdefault(prod, {'variance': 0})['variance'] += actual_val - forecast_val

            # Aggregate for Drilldown Chart
            drilldown_data.setdefault(stor, {'Overforecast': 0, 'Underforecast': 0, 'Accurate': 0, 'products': {}})
            drilldown_data[stor].setdefault('products', {}).setdefault(prod, {'Overforecast': 0, 'Underforecast': 0, 'Accurate': 0, 'timeseries': {}})
            drilldown_data[stor]['products'][prod].setdefault('timeseries', {}).setdefault(date_str, {'Overforecast': 0, 'Underforecast': 0, 'Accurate': 0})
            
            error_percent = ((forecast_val - actual_val) / actual_val) if actual_val != 0 else (1 if forecast_val > 0 else 0)
            status = 'Accurate' if abs(error_percent) <= 0.10 else ('Overforecast' if error_percent > 0 else 'Underforecast')
            
            drilldown_data[stor][status] += 1
            drilldown_data[stor]['products'][prod][status] += 1
            drilldown_data[stor]['products'][prod]['timeseries'][date_str][status] += 1

        # Final formatting for the two new charts
        final_forecast_variance = [{'label': k, 'value': v['variance']} for k, v in forecast_variance.items()]
        drilldown_region = [{'region': k, 'Overforecast': v['Overforecast'], 'Underforecast': v['Underforecast'], 'Accurate': v['Accurate']} for k, v in drilldown_data.items()]
        drilldown_product = {k: [{'product': p_k, 'Overforecast': p_v['Overforecast'], 'Underforecast': p_v['Underforecast'], 'Accurate': p_v['Accurate']} for p_k, p_v in v['products'].items()] for k, v in drilldown_data.items()}
        drilldown_timeseries = {k: {p_k: [{'date': d_k, **d_v} for d_k, d_v in p_v['timeseries'].items()] for p_k, p_v in v['products'].items()} for k, v in drilldown_data.items()}

        final_drilldown_data = {
            "regionData": drilldown_region, "productData": drilldown_product, "timeSeriesData": drilldown_timeseries
        }
        return {
            "filters": {
                "productList": product_list,
                "storeList": store_list,
                "modelList": model_list,
                "minDate": min_date,
                "maxDate": max_date
            },
            "kpiData": kpiData,
            "timeseries": timeseries,
            "productSalesBreakdown": product_sales_breakdown,
            "forecastVariance": final_forecast_variance,
            "drilldownErrorData": final_drilldown_data
        }

def safe_float(val):
    if val is None:
        return ""
    try:
        return float(val)
    except:
        return val

@router.get("/planner-data")
async def get_planner_data(
    conn=Depends(get_hana_connection),
    current_user: str = Depends(get_current_user),
    forecastid: int = None,
    product: str = Query(None),
    store: str = Query(None),
    start: str = Query(None),
    end: str = Query(None)
):
    try:
        with conn.cursor() as cur:
            # Step 1: Find the most recent FORECASTID from FORECASTDATA
            if forecastid is None:
                cur.execute("SELECT MAX(FORECASTID) FROM DBADMIN.FORECASTDATA")
                row = cur.fetchone()
                forecastid = row[0] if row and row[0] is not None else -1

            if forecastid == -1:
                return JSONResponse(status_code=200, content={"status": "success", "data": []})

            # Step 2: Build the filter clauses
            where_clauses = ["f.FORECASTID = ?"]
            params = [forecastid]
            if product: where_clauses.append("f.PRODUCTID = ?"); params.append(product)
            if store: where_clauses.append("f.STOREID = ?"); params.append(store)
            if start: where_clauses.append("f.FORECASTDATE >= ?"); params.append(start)
            if end: where_clauses.append("f.FORECASTDATE <= ?"); params.append(end)
            where_str = " AND ".join(where_clauses)

            # Step 3: Run the main query joining the two tables
            sql_query = f"""
            SELECT
                f.STOREID AS "store",
                f.PRODUCTID AS "product",
                f.FORECASTDATE AS "date",
                f.HISTORICALDEMAND AS "actual_quantity",
                f.PREDICTEDDEMAND AS "forecast_quantity",
                f.MANUALDEMAND AS "MANUALDEMAND",
                a.ACTUAL_UNITS AS "planner_entered_actuals",
                f.MANUALDEMAND AS "final_qty"
            FROM
                DBADMIN.FORECASTDATA AS f
            LEFT JOIN
                DBADMIN.ACTUALS_DATA AS a ON f.PRODUCTID = a.PRODUCTID AND f.STOREID = a.STOREID AND f.FORECASTDATE = a.SALESDATE
            WHERE {where_str}
            ORDER BY f.STOREID, f.PRODUCTID, f.FORECASTDATE
            """
            cur.execute(sql_query, params)
            
            rows = cur.fetchall()
            columns = [desc[0].lower() for desc in cur.description]
            result = [dict(zip(columns, row)) for row in rows]
            
            for row in result:
                for key, value in row.items():
                    if isinstance(value, Decimal):
                        # Convert Decimal to float if it's not None
                        row[key] = float(value) if value is not None else None
                
                # Also ensure date is a string and final_qty logic is applied
                row['date'] = str(row['date']) if row.get('date') else None
                row['final_qty'] = row.get('manualdemand') if row.get('manualdemand') is not None else row.get('forecast_quantity')

            return JSONResponse(status_code=200, content={"status": "success", "data": result})

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching planner data: {str(e)}")


@router.post("/planner-data")
async def update_planner_data(
    request: Request,
    conn=Depends(get_hana_connection),
    current_user: str = Depends(get_current_user),
):
    updates = await request.json()
    if not updates:
        return {"status": "success", "message": "No updates provided."}

    with conn.cursor() as cur:
        for edit in updates:
            store = edit.get("store")
            product = edit.get("product")
            date = edit.get("date")
            reason = edit.get("reason", "")
            comment = edit.get("comment", "")
            
            # --- Logic to update MANUALDEMAND in FORECASTDATA ---
            if 'MANUALDEMAND' in edit and edit['MANUALDEMAND'] is not None:
                manual_forecast = edit['MANUALDEMAND']
                cur.execute(
                    """
                    UPDATE DBADMIN.FORECASTDATA
                    SET MANUALDEMAND = ?
                    WHERE STOREID = ? AND PRODUCTID = ? AND FORECASTDATE = ?
                      AND FORECASTID = (SELECT MAX(FORECASTID) FROM DBADMIN.FORECASTDATA)
                    """,
                    (manual_forecast, store, product, date)
                )
                # Log this specific change
                cur.execute(
                    """
                    INSERT INTO WORKBENCH_EDIT (USER, REASON, COMMENT, STOREID, PRODUCTID, FORECASTDATE, NEWVALUE)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (current_user, reason, f"Updated Manual Forecast: {comment}", store, product, date, manual_forecast)
                )

            # --- Logic to UPSERT planner_entered_actuals into ACTUALS_DATA ---
            if 'planner_entered_actuals' in edit and edit['planner_entered_actuals'] is not None:
                planner_actuals = edit['planner_entered_actuals']
                cur.execute(
                    """
                    MERGE INTO DBADMIN.ACTUALS_DATA AS target
                    USING (SELECT ? AS PRODUCTID, ? AS STOREID, ? AS SALESDATE, ? AS ACTUAL_UNITS, ? AS USER FROM DUMMY) AS source
                    ON target.PRODUCTID = source.PRODUCTID AND target.STOREID = source.STOREID AND target.SALESDATE = source.SALESDATE
                    WHEN MATCHED THEN
                        UPDATE SET target.ACTUAL_UNITS = source.ACTUAL_UNITS, target.ENTERED_BY = source.USER, target.ENTRY_TIMESTAMP = CURRENT_UTCTIMESTAMP
                    WHEN NOT MATCHED THEN
                        INSERT (PRODUCTID, STOREID, SALESDATE, ACTUAL_UNITS, ENTERED_BY)
                        VALUES (source.PRODUCTID, source.STOREID, source.SALESDATE, source.ACTUAL_UNITS, source.USER);
                    """,
                    (product, store, date, planner_actuals, current_user)
                )
                 # Log this specific change
                cur.execute(
                    """
                    INSERT INTO WORKBENCH_EDIT (USER, REASON, COMMENT, STOREID, PRODUCTID, FORECASTDATE, NEWVALUE)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (current_user, reason, f"Updated Planner Actuals: {comment}", store, product, date, planner_actuals)
                )

    conn.commit()
    return {"status": "success", "message": "Planner data updated."}


def aggregate_data(df, time_bucket, forecast_type='Overall', item_col=None, organization_id='default'):
    """
    Aggregate time series data from daily to specified time bucket
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame with Date and Demand columns
    time_bucket : str
        Target aggregation level: "Daily", "Weekly", "Monthly", "Quarterly", "Yearly"
    forecast_type : str
        Type of forecast: "Overall", "Item-wise", "Store-Item Combination"
    item_col : str, optional
        Column name for item grouping (ProductID, store_item, etc.)
    organization_id : str, optional
        Organization identifier for calendar configuration (default: 'default')
    
    Returns:
    --------
    pandas.DataFrame
        Aggregated DataFrame
    """
    try:
        print(f"Starting aggregation: {time_bucket} for {forecast_type} (Organization: {organization_id})")
        
        # Make a copy to avoid modifying original data
        df_agg = df.copy()
        
        # Ensure Date column is datetime
        if 'Date' not in df_agg.columns:
            raise ValueError("Date column is required for aggregation")
        
        df_agg['Date'] = pd.to_datetime(df_agg['Date'])
        
        # If already Daily or no aggregation needed, return as-is
        if time_bucket == "Daily":
            print("No aggregation needed - already Daily")
            return df_agg
        
        # Create aggregation period
        if time_bucket == "Weekly":
            # Get organization-specific week rule
            week_rule = OrganizationCalendarConfig.get_pandas_week_rule(organization_id)
            week_start_name = OrganizationCalendarConfig.get_week_start_name(organization_id)
            print(f"Using week rule {week_rule} (week starts on {week_start_name}) for organization {organization_id}")
            
            # Group by week using organization's calendar
            df_agg['AggPeriod'] = df_agg['Date'].dt.to_period(week_rule)
        elif time_bucket == "Monthly":
            # Group by month
            df_agg['AggPeriod'] = df_agg['Date'].dt.to_period('M')
        elif time_bucket == "Quarterly":
            # Group by quarter
            df_agg['AggPeriod'] = df_agg['Date'].dt.to_period('Q')
        elif time_bucket == "Yearly":
            # Group by year
            df_agg['AggPeriod'] = df_agg['Date'].dt.to_period('Y')
        else:
            print(f"Unknown time_bucket: {time_bucket}, defaulting to Daily")
            return df_agg
        
        # Define aggregation columns based on forecast type
        group_cols = ['AggPeriod']
        
        if forecast_type == "Item-wise" and item_col and item_col in df_agg.columns:
            group_cols.append(item_col)
            print(f"Adding {item_col} to grouping for item-wise aggregation")
        elif forecast_type == "Store-Item Combination":
            if 'StoreID' in df_agg.columns and 'ProductID' in df_agg.columns:
                group_cols.extend(['StoreID', 'ProductID'])
                print("Adding StoreID and ProductID to grouping for store-item aggregation")
            elif item_col and item_col in df_agg.columns:
                group_cols.append(item_col)
                print(f"Adding {item_col} to grouping for store-item aggregation")
        
        # Define aggregation functions
        agg_functions = {
            'Demand': 'sum',  # Sum demand over the period
            'Date': 'first'   # Take first date of the period
        }
        
        # Add other numeric columns with sum aggregation
        numeric_cols = df_agg.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if col not in ['Demand'] and col in df_agg.columns:
                agg_functions[col] = 'sum'
        
        # Add categorical columns with first value
        categorical_cols = df_agg.select_dtypes(include=['object', 'category']).columns
        for col in categorical_cols:
            if col not in group_cols and col != 'Date' and col in df_agg.columns:
                agg_functions[col] = 'first'
        
        print(f"Grouping by: {group_cols}")
        print(f"Aggregation functions: {agg_functions}")
        
        # Perform aggregation
        df_aggregated = df_agg.groupby(group_cols).agg(agg_functions).reset_index()
        
        # Convert period back to datetime for the first day of the period
        df_aggregated['Date'] = df_aggregated['AggPeriod'].dt.start_time
        df_aggregated = df_aggregated.drop('AggPeriod', axis=1)
        
        # Sort by date and other grouping columns
        sort_cols = ['Date']
        if len(group_cols) > 1:  # If we have item grouping columns
            sort_cols.extend([col for col in group_cols[1:] if col in df_aggregated.columns])
        
        df_aggregated = df_aggregated.sort_values(sort_cols).reset_index(drop=True)
        
        print(f"Aggregation complete:")
        print(f"  Original shape: {df.shape}")
        print(f"  Aggregated shape: {df_aggregated.shape}")
        print(f"  Date range: {df_aggregated['Date'].min()} to {df_aggregated['Date'].max()}")
        print(f"  Organization calendar: {week_start_name} start week" if time_bucket == "Weekly" else "")
        
        return df_aggregated
        
    except Exception as e:
        print(f"Error in aggregation: {str(e)}")
        print("Returning original DataFrame without aggregation")
        return df

def generate_future_dates_from_current(horizon, frequency='D', organization_id='default'):
    """
    Generate future dates starting from tomorrow (current date + 1 period)
    based on the specified frequency and organization calendar.
    
    Args:
        horizon (int): Number of periods to forecast
        frequency (str): Data frequency ('D', 'W', 'M', 'Q', 'Y')
        organization_id (str): Organization identifier for calendar configuration
    
    Returns:
        pd.DatetimeIndex: Future dates starting from next period
    """
    try:
        current_date = pd.Timestamp.now().normalize()  # Current date at midnight
        
        # Map frequency to appropriate start date calculation
        if frequency == 'D':
            start_date = current_date + pd.Timedelta(days=1)  # Tomorrow
        elif frequency == 'W':
            # For weekly, align with organization's week start day
            week_start_day = OrganizationCalendarConfig.get_week_start_day(organization_id)
            week_start_name = OrganizationCalendarConfig.get_week_start_name(organization_id)
            
            # Calculate days until next week starts according to organization calendar
            current_weekday = current_date.weekday()  # 0=Monday, 6=Sunday
            days_until_next_week = (week_start_day - current_weekday) % 7
            if days_until_next_week == 0:  # If today is the week start day, go to next week
                days_until_next_week = 7
                
            start_date = current_date + pd.Timedelta(days=days_until_next_week)
            logging.info(f"Weekly forecast for organization {organization_id}: week starts on {week_start_name}, next week starts {start_date.strftime('%Y-%m-%d')}")
        elif frequency == 'M':
            start_date = current_date + pd.DateOffset(months=1)  # Next month
        elif frequency == 'Q':
            start_date = current_date + pd.DateOffset(months=3)  # Next quarter
        elif frequency == 'Y':
            start_date = current_date + pd.DateOffset(years=1)   # Next year
        else:
            start_date = current_date + pd.Timedelta(days=1)     # Default to tomorrow
        
        # For weekly frequency, use organization-specific week rule
        if frequency == 'W':
            week_rule = OrganizationCalendarConfig.get_pandas_week_rule(organization_id)
            future_dates = pd.date_range(
                start=start_date,
                periods=horizon,
                freq=week_rule
            )
        else:
            # Generate the date range for non-weekly frequencies
            future_dates = pd.date_range(
                start=start_date,
                periods=horizon,
                freq=frequency
            )
        
        logging.info(f"Generated {len(future_dates)} future dates from {start_date.strftime('%Y-%m-%d')} with frequency {frequency} for organization {organization_id}")
        return future_dates
        
    except Exception as e:
        logging.error(f"Error generating future dates: {e}")
        # Fallback to simple daily dates from tomorrow
        current_date = pd.Timestamp.now().normalize()
        return pd.date_range(
            start=current_date + pd.Timedelta(days=1),
            periods=horizon,
            freq='D'
        )

class OrganizationCalendarRequest(BaseModel):
    organization_id: str
    week_start_day: int  # 0=Monday, 6=Sunday

class OrganizationCalendarResponse(BaseModel):
    organization_id: str
    week_start_day: int
    week_start_name: str
    pandas_rule: str

# Add these new endpoints for organization calendar management
@router.post("/organization/calendar")
async def set_organization_calendar(
    request: OrganizationCalendarRequest,
    current_user: str = Depends(get_current_user)
):
    """
    Set or update organization calendar configuration.
    
    Args:
        organization_id: Unique identifier for the organization
        week_start_day: Day of week that starts the business week (0=Monday, 6=Sunday)
    """
    try:
        OrganizationCalendarConfig.add_organization_calendar(
            request.organization_id, 
            request.week_start_day
        )
        
        return {
            "status": "success",
            "message": f"Calendar configuration updated for organization {request.organization_id}",
            "organization_id": request.organization_id,
            "week_start_day": request.week_start_day,
            "week_start_name": OrganizationCalendarConfig.get_week_start_name(request.organization_id),
            "pandas_rule": OrganizationCalendarConfig.get_pandas_week_rule(request.organization_id)
        }
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Failed to update calendar configuration: {str(e)}"}

@router.get("/organization/calendar/{organization_id}")
async def get_organization_calendar(
    organization_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    Get organization calendar configuration.
    """
    try:
        return OrganizationCalendarResponse(
            organization_id=organization_id,
            week_start_day=OrganizationCalendarConfig.get_week_start_day(organization_id),
            week_start_name=OrganizationCalendarConfig.get_week_start_name(organization_id),
            pandas_rule=OrganizationCalendarConfig.get_pandas_week_rule(organization_id)
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to get calendar configuration: {str(e)}"}

@router.get("/organization/calendars")
async def list_organization_calendars(
    current_user: str = Depends(get_current_user)
):
    """
    List all organization calendar configurations.
    """
    try:
        calendars = []
        for org_id, week_start in OrganizationCalendarConfig.ORGANIZATION_WEEK_START.items():
            calendars.append(OrganizationCalendarResponse(
                organization_id=org_id,
                week_start_day=week_start,
                week_start_name=OrganizationCalendarConfig.get_week_start_name(org_id),
                pandas_rule=OrganizationCalendarConfig.get_pandas_week_rule(org_id)
            ))
        return {"calendars": calendars}
    except Exception as e:
        return {"status": "error", "message": f"Failed to list calendar configurations: {str(e)}"}

@router.post("/create-user", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, conn=Depends(get_hana_connection), current_user: dict = Depends(get_current_user)):
    cur = conn.cursor()
    try:
        # FIX: Manually determine the next available USERID
        cur.execute("SELECT MAX(USERID) FROM DBADMIN.USERS")
        max_id_record = cur.fetchone()
        # If the table is empty, max_id_record[0] will be None. Default to 0.
        next_id = (max_id_record[0] or 0) + 1

        cur.execute(
            """
            INSERT INTO DBADMIN.USERS
                  (USERID, ORGID, USERNAME, EMAIL, PASSWORDHASH,
                   ROLE, ISACTIVE, EMPLOYEEID, FULLNAME)
            VALUES (?, 1, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                next_id,                        
                payload.email,                  
                payload.email,
                bcrypt.hash(payload.password),  
                payload.role,
                payload.employee_id,
                payload.full_name,
            ),
        )
        conn.commit()
        
        # We already know the new ID, so we don't need to query for it again.
        return UserOut(
            userid=next_id,
            full_name=payload.full_name,
            email=payload.email,
            role=payload.role,
            employee_id=payload.employee_id,
            org_id=1,
            isactive=True,
        )
    except Exception as e:
        conn.rollback()
        raise HTTPException(400, f"Create user failed: {e}")
    finally:
        cur.close()

@router.get("/list-users", response_model=list[UserOut])
async def list_users(conn=Depends(get_hana_connection), current_user: dict = Depends(get_current_user)):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT USERID, FULLNAME, EMAIL, ROLE,
               EMPLOYEEID, ORGID, ISACTIVE
        FROM   DBADMIN.USERS
        ORDER  BY USERID
        """
    )
    rows = cur.fetchall()
    cur.close()
    return [
        UserOut(
            userid=r[0],
            full_name=r[1],
            email=r[2],
            role=r[3],
            employee_id=r[4],
            org_id=r[5],
            isactive=bool(r[6]),
        )
        for r in rows
    ]


@router.patch("/user-status/{userid}", response_model=dict)
async def update_user_status(
    userid: int = Path(..., gt=0),
    isactive: bool = Query(True),
    conn=Depends(get_hana_connection),
    
):
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE DBADMIN.USERS
            SET ISACTIVE = ?
            WHERE USERID = ?
            """,
            (1 if isactive else 0, userid),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, f"User {userid} not found.")
        conn.commit()
        return {"userid": userid, "isactive": isactive, "status": "updated"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(400, f"Update failed: {e}")
    finally:
        cur.close()


@router.delete("/user/{userid}", status_code=status.HTTP_200_OK)
async def delete_user(
    userid: int = Path(..., gt=0, description="The ID of the user to delete"),
    conn=Depends(get_hana_connection),
    current_user: dict = Depends(get_current_user)
):
    """
    Deletes a user from the database.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM DBADMIN.USERS WHERE USERID = ?",
            (userid,),
        )
        
        # Check if a row was actually deleted
        if cur.rowcount == 0:
            conn.rollback()
            raise HTTPException(status_code=404, detail=f"User with ID {userid} not found.")
            
        conn.commit()
        return {"status": "success", "message": f"User {userid} has been deleted."}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {e}")
    finally:
        cur.close()