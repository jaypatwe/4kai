import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import Cookies from "js-cookie";
import Papa from "papaparse";
import * as XLSX from "xlsx";
import { UPLOAD_CLEANED_DATA_ENDPOINT, MODELS_ENDPOINT, BASE_URL, RUN_FORECAST_ENDPOINT } from './config';
import PageTitle from './PageTitle';
import "../App.css";

// Add custom CSS for forecast displays
const customStyles = `
  /* Table Container Styles */
  .table-container {
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    margin-bottom: 20px;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    -webkit-overflow-scrolling: touch; /* Smooth scrolling on iOS */
  }

  /* Common Table Styles */
  .future-forecasts table, 
  .imported-data-table table, 
  .model-results table {
    width: 100%;
    min-width: 650px; /* Minimum width to ensure readability */
    border-collapse: collapse;
    margin-bottom: 0; /* Remove bottom margin as container has margin */
    font-size: 14px;
    font-family: Arial, sans-serif;
  }
  
  /* Wrap all tables in a container */
  .future-forecasts,
  .imported-data-table,
  .model-results {
    width: 100%;
    overflow-x: auto;
    margin-bottom: 20px;
    background: #ffffff;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    padding: 1px; /* Prevent margin collapse */
  }
  
  .future-forecasts th, .future-forecasts td,
  .imported-data-table th, .imported-data-table td,
  .model-results th, .model-results td {
    border: 1px solid #d4d4d4;
    padding: 8px 12px;
    height: 21px;
    min-width: 100px; /* Minimum width for columns */
    max-width: 300px; /* Maximum width for columns */
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    background-color: #ffffff;
  }
  
  .future-forecasts th, .imported-data-table th, .model-results th {
    background-color: #f8f9fa;
    font-weight: 600;
    color: #000000;
    position: sticky;
    top: 0;
    z-index: 1;
    border-bottom: 2px solid #d4d4d4;
  }

  /* Ensure the forecast container doesn't overflow */
  .forecast-container {
    width: 100%;
    max-width: 100%;
    overflow-x: hidden;
    padding: 20px;
    box-sizing: border-box;
  }

  /* Make sure item and combo forecasts don't overflow */
  .item-forecast,
  .combo-forecast {
    width: 100%;
    overflow-x: auto;
    margin-bottom: 30px;
    padding: 15px;
    border: 1px solid #ddd;
    border-radius: 4px;
    background-color: white;
  }

  /* Rest of your existing styles... */
  .item-selector, .combination-selector {
    margin-bottom: 15px;
  }
  
  .item-selector select, .combination-selector select {
    padding: 8px;
    border-radius: 4px;
    border: 1px solid #ccc;
    min-width: 250px;
  }
  
  .unknown-forecast-type {
    padding: 15px;
    background-color: #fff3cd;
    border: 1px solid #ffeeba;
    border-radius: 4px;
    color: #856404;
  }
  
  .unknown-forecast-type pre {
    background-color: #f8f9fa;
    padding: 10px;
    border-radius: 4px;
    overflow-x: auto;
  }

  .download-button {
    background-color: #4CAF50;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: background-color 0.3s ease;
    margin-top: 15px;
  }

  .download-button:hover {
    background-color: #45a049;
  }

  .download-button:disabled {
    background-color: #cccccc;
    cursor: not-allowed;
  }

  .download-button svg {
    width: 16px;
    height: 16px;
  }

  .forecast-results-section {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 20px;
    margin-top: 20px;
  }

  .forecast-results-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
  }

  .forecast-results-title {
    font-size: 18px;
    font-weight: 600;
    color: #333;
    margin: 0;
  }

  /* Preview Table Specific Styles */
  .preview-table-container {
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    margin: 20px 0;
    background: #fff;
    border-radius: 4px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    -webkit-overflow-scrolling: touch;
    position: relative;
  }

  .preview-table-container table {
    width: auto; /* Allow table to take necessary width */
    border-collapse: collapse;
    font-size: 12px;
    font-family: Arial, sans-serif;
    white-space: nowrap;
  }

  .preview-table-container th,
  .preview-table-container td {
    padding: 4px 6px;
    border: 1px solid #e0e0e0;
    text-align: left;
    height: 20px;
    line-height: 20px;
    min-width: 100px; /* Minimum width for columns */
    background-color: #ffffff;
  }

  /* Ensure text is visible in cells */
  .preview-table-container td {
    white-space: nowrap;
    overflow: visible; /* Make content visible */
    text-overflow: clip;
    max-width: none; /* Remove max-width constraint */
  }

  .preview-table-container th {
    background-color: #f3f3f3;
    font-weight: normal;
    color: #000000;
    position: sticky;
    top: 0;
    z-index: 1;
    border-bottom: 2px solid #d4d4d4;
    height: 22px;
    line-height: 22px;
    white-space: nowrap;
    overflow: visible; /* Make header text visible */
  }

  .preview-table-container tr:nth-child(even) {
    background-color: #fafafa;
  }

  .preview-table-container tr:hover td {
    background-color: #f0f7ff;
  }

  /* Scrollbar styling for better visibility */
  .preview-table-container::-webkit-scrollbar {
    height: 8px;
    width: 8px;
  }

  .preview-table-container::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
  }

  .preview-table-container::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 4px;
  }

  .preview-table-container::-webkit-scrollbar-thumb:hover {
    background: #666;
  }

  /* Container for the entire preview section */
  .imported-data-table {
    width: 100%;
    max-width: 100%;
    overflow: hidden; /* Prevent outer container overflow */
    padding: 0 1px; /* Prevent scrollbar from causing page overflow */
  }

  .holiday-config-section {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 20px;
    margin-top: 25px;
    margin-bottom: 25px;
  }
  
  .holiday-config-section h4 {
    font-size: 18px;
    font-weight: 600;
    color: #333;
    margin-top: 0;
    margin-bottom: 20px;
  }

  .config-item {
    display: flex;
    align-items: center;
    margin-bottom: 15px;
    font-size: 15px;
  }

  .config-item input[type="checkbox"] {
    margin-right: 10px;
    width: 16px;
    height: 16px;
    cursor: pointer;
  }

  .config-item select {
    padding: 6px 10px;
    border-radius: 4px;
    border: 1px solid #ccc;
    font-size: 14px;
    background-color: white;
  }

  .custom-holiday-form {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 20px;
    padding-top: 15px;
    border-top: 1px solid #e0e0e0;
  }

  .custom-holiday-form h5 {
    margin: 0;
    font-size: 16px;
    font-weight: 500;
  }

  .custom-holiday-form input[type="text"],
  .custom-holiday-form input[type="date"] {
    padding: 8px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 14px;
  }

  .custom-holiday-form button {
    padding: 8px 15px;
    background-color: #007bff;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
    transition: background-color 0.2s;
  }

  .custom-holiday-form button:hover {
    background-color: #0056b3;
  }

  .custom-holiday-list {
    margin-top: 15px;
    padding-left: 10px;
  }

  .custom-holiday-list h6 {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .custom-holiday-list ul {
    list-style-type: none;
    padding: 0;
    margin: 0;
  }

  .custom-holiday-list li {
    display: flex;
    align-items: center;
    background-color: #e9ecef;
    padding: 5px 10px;
    border-radius: 4px;
    margin-bottom: 5px;
    font-size: 14px;
    justify-content: space-between;
  }

  .custom-holiday-list li button {
    background: none;
    border: none;
    color: #dc3545;
    font-size: 18px;
    font-weight: bold;
    cursor: pointer;
    padding: 0 5px;
    line-height: 1;
  }

  .multi-select-dropdown {
    position: relative;
    width: 100%;
    max-width: 400px; /* Or whatever width you prefer */
  }

  .multi-select-selected {
    padding: 8px 12px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background-color: white;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: 38px;
  }

  .multi-select-placeholder {
    color: #757575;
  }

  .multi-select-options {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background-color: white;
    border: 1px solid #ccc;
    border-top: none;
    border-radius: 0 0 4px 4px;
    z-index: 1000;
    max-height: 200px;
    overflow-y: auto;
  }

  .multi-select-option {
    padding: 10px 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
  }
  
  .multi-select-option:hover {
    background-color: #f0f7ff;
  }

  .multi-select-option input[type="checkbox"] {
    margin-right: 10px;
  }

  .multi-select-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }

  .multi-select-pill {
    background-color: #e0e7ff;
    color: #4338ca;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
`;

// Helper function to generate future dates from current date
const generateFutureDatesFromCurrent = (horizon, frequency = 'daily') => {
  const currentDate = new Date();
  const futureDates = [];
  
  for (let i = 1; i <= horizon; i++) {
    const futureDate = new Date(currentDate);
    
    switch (frequency.toLowerCase()) {
      case 'daily':
        futureDate.setDate(currentDate.getDate() + i);
        break;
      case 'weekly':
        futureDate.setDate(currentDate.getDate() + (i * 7));
        break;
      case 'monthly':
        futureDate.setMonth(currentDate.getMonth() + i);
        break;
      case 'quarterly':
        futureDate.setMonth(currentDate.getMonth() + (i * 3));
        break;
      case 'yearly':
        futureDate.setFullYear(currentDate.getFullYear() + i);
        break;
      default:
        futureDate.setDate(currentDate.getDate() + i);
    }
    
    futureDates.push(futureDate);
  }
  
  return futureDates;
};

// Helper function to detect data frequency from historical dates
const detectDataFrequency = (dates) => {
  if (!dates || dates.length < 2) return 'daily';
  
  const sortedDates = dates.map(d => new Date(d)).sort((a, b) => a - b);
  const diffs = [];
  
  for (let i = 1; i < Math.min(sortedDates.length, 10); i++) {
    const diff = (sortedDates[i] - sortedDates[i-1]) / (1000 * 60 * 60 * 24); // days
    diffs.push(diff);
  }
  
  const avgDiff = diffs.reduce((a, b) => a + b, 0) / diffs.length;
  
  if (avgDiff <= 1.5) return 'daily';
  if (avgDiff >= 6 && avgDiff <= 8) return 'weekly';
  if (avgDiff >= 28 && avgDiff <= 32) return 'monthly';
  if (avgDiff >= 88 && avgDiff <= 95) return 'quarterly';
  if (avgDiff >= 360 && avgDiff <= 370) return 'yearly';
  
  return 'daily'; // fallback
};

function ItemWiseTable({ csvData }) {
  const items = useMemo(() => [...new Set(csvData.map(row => row.Item))], [csvData]);
  const [selectedItem, setSelectedItem] = useState(items[0] || "");

  useEffect(() => {
    if (items.length > 0 && !items.includes(selectedItem)) {
      setSelectedItem(items[0]);
    }
  }, [items, selectedItem]);

  const filteredData = useMemo(
    () => csvData.filter(row => row.Item === selectedItem),
    [csvData, selectedItem]
  );

  return (
    <div className="item-forecast">
      <div className="item-selector">
        <label>Select Item: </label>
        <select value={selectedItem} onChange={e => setSelectedItem(e.target.value)}>
          {items.map(item => <option key={item} value={item}>{item}</option>)}
        </select>
      </div>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Model</th>
              <th>Forecast</th>
              <th>Run Type</th>
            </tr>
          </thead>
          <tbody>
            {filteredData.map((row, idx) => (
              <tr key={idx}>
                <td>{row.Date}</td>
                <td>{row.Model}</td>
                <td>{typeof row.Forecast === 'number' ? row.Forecast.toFixed(2) : row.Forecast}</td>
                <td>{row.RunType}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StoreItemComboTable({ csvData }) {
  const combos = useMemo(
    () => [...new Set(csvData.map(row => `${row.Store} - ${row.Item}`))],
    [csvData]
  );
  const [selectedCombo, setSelectedCombo] = useState(combos[0] || "");

  useEffect(() => {
    if (combos.length > 0 && !combos.includes(selectedCombo)) {
      setSelectedCombo(combos[0]);
    }
  }, [combos, selectedCombo]);

  const filteredData = useMemo(
    () => csvData.filter(row => `${row.Store} - ${row.Item}` === selectedCombo),
    [csvData, selectedCombo]
  );

  return (
    <div className="combo-forecast">
      <div className="combination-selector">
        <label>Select Store-Item Combination: </label>
        <select value={selectedCombo} onChange={e => setSelectedCombo(e.target.value)}>
          {combos.map(combo => <option key={combo} value={combo}>{combo}</option>)}
        </select>
      </div>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Model</th>
              <th>Forecast</th>
              <th>Run Type</th>
            </tr>
          </thead>
          <tbody>
            {filteredData.map((row, idx) => (
              <tr key={idx}>
                <td>{row.Date}</td>
                <td>{row.Model}</td>
                <td>{typeof row.Forecast === 'number' ? row.Forecast.toFixed(2) : row.Forecast}</td>
                <td>{row.RunType}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


const ForecastSettings = () => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedModels, setSelectedModels] = useState([]);
  const [timeBucket, setTimeBucket] = useState("Daily");
  const [detectedDataFrequency, setDetectedDataFrequency] = useState('daily');
  const [forecastHorizon, setForecastHorizon] = useState("0");
  const [forecastLock, setForecastLock] = useState("0");
  const [granularity, setGranularity] = useState("Overall");
  const [aggregation, setAggregation] = useState("Sum");
  const [forecastMethod, setForecastMethod] = useState("Best Fit");
  const [canRunModel, setCanRunModel] = useState(false);

  const [uploadedDatasets, setUploadedDatasets] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState("");
  const [importedData, setImportedData] = useState([]);
  const [columnNames, setColumnNames] = useState([]);
  const [showColumns, setShowColumns] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const [columnMappings, setColumnMappings] = useState({});
  const [timeDependentVariables, setTimeDependentVariables] = useState([]);
  const [omittedColumns, setOmittedColumns] = useState([]);
  const [models, setModels] = useState([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [dataSummary, setDataSummary] = useState(null);
  const [showSummary, setShowSummary] = useState(false);
  const columnSelectionRef = useRef(null);
  const uploadButtonRef = useRef(null);
  const [forecastResults, setForecastResults] = useState(null);
  const [skippedItems, setSkippedItems] = useState([]);
  const [showForecastResults, setShowForecastResults] = useState(false);
  const [bestFitMetric, setBestFitMetric] = useState("MAE");
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);

  // New variables for holidays
  const [useStandardHolidays, setUseStandardHolidays] = useState(true);
  const [holidayCountry, setHolidayCountry] = useState('US');

  const mandatoryFields = ["Date", "Demand", "StoreID", "ProductID"];

  const measureOptions = ["Sales History", "Inventory Levels", "Demand Trends"];

  const pluralTimeUnit = useMemo(() => {
    if (!timeBucket) return 'periods'; // Fallback for safety
    
    const lowerCaseBucket = timeBucket.toLowerCase();

    if (lowerCaseBucket === 'daily') {
      return 'days';
    }
    // This works for 'weekly', 'monthly', 'yearly'
    return lowerCaseBucket.replace(/ly$/, 's');
  }, [timeBucket]);

  const granularityOptions = [
    "Overall",
    "ProductID-wise",
    "StoreID-ProductID Combination",
  ];
  // Alert state
    const [alert, setAlert] = useState({
      isOpen: false,
      message: "",
      type: "info", // 'info', 'success', 'error', 'confirm'
      onConfirm: null
    });
  
    const showAlert = (message, type = "info", onConfirm = null) => {
      setAlert({
        isOpen: true,
        message,
        type,
        onConfirm
      });
    };
  
     // Token retrieval function
   const getAuthToken = useCallback(() => {
     const token = Cookies.get("authToken");
     if (!token) {
       showAlert("Authentication token not found. Please log in to continue.", "error");
       return null;
     }
     return token;
   }, []);

    const fetchFiles = async () => {
      try {
        const token = getAuthToken();
        if (!token) {
          showAlert("No authentication token found. Please log in to continue.", "error");
          return;
        }
        const response = await fetch(`${BASE_URL}/api/engine/files`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to fetch file list: ${response.status} - ${errorText}`);
        }
        const data = await response.json();
        setUploadedDatasets(data.files || []);
      } catch (error) {
        showAlert(`Error fetching files: ${error.message}`, "error");
      }
    };

  useEffect(() => {
    fetchFiles();
    
    // Fetch available forecasting models
    const fetchModels = async () => {
      setIsLoadingModels(true);
      try {
        const token = getAuthToken();
        if (!token) {
          showAlert("No authentication token found. Please log in to continue.", "error");
          return;
        }
        const response = await fetch(MODELS_ENDPOINT, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to fetch models: ${response.status} - ${errorText}`);
        }
        const data = await response.json();
        console.log('Fetched models:', data.models); // Add logging
        setModels(data.models || []);
      } catch (error) {
        console.error('Error fetching models:', error); // Add error logging
        showAlert(`Error fetching models: ${error.message}`, "error");
        // Fallback to default models if API fails
        setModels([
          "Seasonal History",
          "Intermittent History", 
          "Advanced Forecasting"
        ]);
      } finally {
        setIsLoadingModels(false);
      }
    };
    fetchModels();
  }, []);

  const handleDatasetChange = async (event) => {
    const fileName = event.target.value;
    setSelectedDataset(fileName);
    setImportedData([]);
    setColumnNames([]);
    setShowColumns(false);
    setShowTable(false);
    setColumnMappings({});
    setTimeDependentVariables([]);

    if (fileName) {
      try {
        const token = getAuthToken();
        if (!token) {
          console.error("No auth token found, stopping fetch.");
          return;
        }
        const response = await fetch(`${BASE_URL}/api/engine/download/${encodeURIComponent(fileName)}`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
        });
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Fetch failed with status ${response.status}: ${errorText}`);
        }

        const fileType = fileName.split(".").pop().toLowerCase();
        if (fileType === "csv") {
          const text = await response.text();
          Papa.parse(text, {
            complete: (result) => {
              if (result.data && result.data.length > 0) {
                const headers = result.data.length > 1 && typeof result.data[0] === "object"
                  ? Object.keys(result.data[0] || {})
                  : result.data[0] || [];
                const rows = result.data.slice(1).filter(row => row && Object.keys(row).length > 0);
                setColumnNames(Array.isArray(headers) ? headers : [headers]);
                setImportedData(rows);
                setShowColumns(true);

                const dateHeader = headers.find(h => h.toLowerCase() === 'date') || headers[0];
                const dates = result.data.map(row => row[dateHeader]).filter(Boolean);
                const detectedFreq = detectDataFrequency(dates);
                setDetectedDataFrequency(detectedFreq);

                const capitalizedFreq = detectedFreq.charAt(0).toUpperCase() + detectedFreq.slice(1);
                if (['Daily', 'Weekly', 'Monthly', 'Yearly'].includes(capitalizedFreq)) {
                    setTimeBucket(capitalizedFreq);
                }

                setTimeout(() => {
                  if (columnSelectionRef.current) {
                    columnSelectionRef.current.scrollIntoView({ behavior: "smooth" });
                  }
                }, 100);
              } else {
                showAlert("No data or headers found in the selected CSV file.", "error");
              }
            },
            header: true,
            skipEmptyLines: true,
            error: (error) => {
              throw new Error(`Error parsing CSV: ${error.message}`);
            },
          });
        } else if (fileType === "xlsx" || fileType === "xls") {
          const blob = await response.blob();
          const arrayBuffer = await blob.arrayBuffer();
          const workbook = XLSX.read(new Uint8Array(arrayBuffer), { type: "array" });
          const sheetName = workbook.SheetNames[0];
          const worksheet = workbook.Sheets[sheetName];
          const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
          if (jsonData.length > 0) {
            const headers = jsonData[0] || [];
            const rows = jsonData.slice(1).filter(row => row && row.length > 0);
            setColumnNames(Array.isArray(headers) ? headers : [headers]);
            setImportedData(rows);
            setShowColumns(true);
            setTimeout(() => {
              if (columnSelectionRef.current) {
                columnSelectionRef.current.scrollIntoView({ behavior: "smooth" });
              }
            }, 100);
          } else {
            showAlert("No data or headers found in the selected Excel file.", "error");
          }
        }
      } catch (error) {
        console.error("Full preview error:", error);
        showAlert(`Error previewing file: ${error.message}`, "error");
      }
    }
  };

  const handleDeleteColumn = (column) => {
    if (!Array.isArray(columnNames) || !columnNames.includes(column)) return;
    const updatedColumns = columnNames.filter((col) => col !== column);
    setColumnNames(updatedColumns);
    setOmittedColumns([...omittedColumns, { name: column, data: importedData.map(row => row[column]) }]);
  };

  const handleRetrieveColumn = (column) => {
    const omittedColumn = omittedColumns.find(col => col.name === column);
    if (!omittedColumn) return;
    
    const updatedOmittedColumns = omittedColumns.filter(col => col.name !== column);
    const updatedColumns = [...columnNames, column];
    const updatedData = importedData.map((row, index) => ({
      ...row,
      [column]: omittedColumn.data[index]
    }));
    
    setOmittedColumns(updatedOmittedColumns);
    setColumnNames(updatedColumns);
    setImportedData(updatedData);
  };

  const handleMappingChange = (mandatoryField, selectedColumn) => {
    setColumnMappings({
      ...columnMappings,
      [mandatoryField]: selectedColumn,
    });
  };

  const areMandatoryFieldsMapped = () => {
    return mandatoryFields.every(field =>
      columnMappings[field] && columnNames.includes(columnMappings[field])
    );
  };

  const handleShowPreview = () => {
    if (areMandatoryFieldsMapped()) {
      setShowTable(true);
    } else {
      showAlert("Please map the fields first", "error");
    }
  };

  const handleFieldChange = (index, field, value) => {
    const updatedData = [...importedData];
    updatedData[index][field] = value;
    setImportedData(updatedData);
  };

  const handleTimeDependentVariablesChange = (event) => {
    const { value, checked } = event.target;
    setTimeDependentVariables((prev) =>
      checked ? [...prev, value] : prev.filter((item) => item !== value)
    );
    if (checked && uploadButtonRef.current) {
      uploadButtonRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  const handleClearTimeDependentVariables = () => {
    setTimeDependentVariables([]);
  };

  const resetForm = () => {
    setTimeBucket("Daily");
    setForecastHorizon("0");
    setForecastLock("0");
    setGranularity("Overall");
    setAggregation("Sum");
    setForecastMethod("Best Fit");
    setSelectedDataset("");
    setImportedData([]);
    setColumnNames([]);
    setShowColumns(false);
    setShowTable(false);
    setColumnMappings({});
    setTimeDependentVariables([]);
    setSelectedModels("");
  };

  const handleUploadDataForCleaning = async () => {
    if (!areMandatoryFieldsMapped()) {
      showAlert("Please map all mandatory fields before uploading.", "error");
      return;
    }

    try {
      // Create a new dataset with only the mapped fields and time-dependent variables
      const finalData = importedData.map(row => {
        const cleanedRow = {};
        // First add mandatory fields with proper mapping
        mandatoryFields.forEach(field => {
          if (columnMappings[field]) {
            cleanedRow[field] = row[columnMappings[field]];
          }
        });
        // Then add time-dependent variables
        timeDependentVariables.forEach(varName => {
          if (row[varName] !== undefined) {
            cleanedRow[varName] = row[varName];
          }
        });
        return cleanedRow;
      }).filter(row => {
        // Filter out rows with missing mandatory fields
        return mandatoryFields.every(field => row[field] !== undefined && row[field] !== '');
      });

      if (finalData.length === 0) {
        throw new Error("No valid data rows after cleaning. Please check your data and mappings.");
      }

      // Show data sample info
      showAlert(`Processing ${finalData.length} rows of data...`, "info");

      const csv = Papa.unparse(finalData);
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const formData = new FormData();
      const timestamp = new Date().toISOString().replace(/[:.-]/g, "_");
      const newFilename = `${selectedDataset.split('.')[0]}_cleaned_${timestamp}.csv`;
      formData.append("file", blob, newFilename);
      
      // Add metadata with complete information
      formData.append("granularity", granularity || "Overall");
      formData.append("timeBucket", timeBucket || "Daily");
      formData.append("forecastHorizon", forecastHorizon || "30");
      formData.append("columnMappings", JSON.stringify(columnMappings || {}));
      formData.append("timeDependentVariables", JSON.stringify(timeDependentVariables || []));
      formData.append("organizationId", organizationId || "default");

      setIsLoading(true);
      const token = getAuthToken();
      if (!token) {
        showAlert("No authentication token found. Please log in to continue.", "error");
        return;
      }

      showAlert("Uploading data for processing...", "info");

      const response = await fetch(UPLOAD_CLEANED_DATA_ENDPOINT, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Upload failed with status ${response.status}: ${errorText}`);
      }

      const result = await response.json();
      
      if (result.status === "success") {
        showAlert(`Data processed successfully! New file '${newFilename}' created.`, "success");
        // Refresh the datasets list to include the new file
        fetchFiles();
        // Show statistics or summary if available
        if (result.summary) {
          setDataSummary(result.summary);
          setShowSummary(true);
        }
      } else {
        throw new Error(result.message || "Unknown error occurred");
      }
    } catch (error) {
      showAlert(`Error processing data: ${error.message}`, "error");
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleRunModel = async () => {
    if (!canRunModel) {
      showAlert("Please fill all required fields first.", "error");
      return;
    }
    
    setIsLoading(true);
    
    try {
      const token = getAuthToken();
      if (!token) {
        showAlert("No authentication token found. Please log in to continue.", "error");
        return;
      }

      const requestBody = {
        filename: selectedDataset,
        granularity: granularity,
        forecastHorizon: parseInt(forecastHorizon),
        timeBucket: timeBucket,
        forecastLock: parseInt(forecastLock),
        selectedModels: selectedModels, 
        timeDependentVariables: timeDependentVariables,
        columnMappings: columnMappings,
        bestFitMetric: forecastMethod === "Best Fit" ? bestFitMetric : null, 
        holiday_config: { 
          use_standard: useStandardHolidays,
          country: holidayCountry
        }
      };

      showAlert("Running forecast model...", "info");

      const response = await fetch(RUN_FORECAST_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify(requestBody)
      });

      const result = await response.json();
      
      if (!response.ok || result.status === "error") {
        throw new Error(result.message || result.detail || `API responded with status ${response.status}`);
      }
      
      setIsLoading(false);
      
      if (result.status === "success") {
        setForecastResults(result);
        setShowForecastResults(true);
        if (Array.isArray(result.skipped_items) && result.skipped_items.length > 0) {
          setSkippedItems(result.skipped_items);
        } else {
          setSkippedItems([]);
        }

        const newSummary = {
          "Forecast Type": result.forecast_type ?? 'N/A',
          "Granularity Setting": result.config?.granularity ?? 'N/A',
          "Time Bucket": result.config?.timeBucket ?? 'N/A',
          "Forecast Horizon": result.config?.forecastHorizon ?? 'N/A',
          "Models Run": (result.config?.selectedModels?.length > 0) ? result.config.selectedModels.join(', ') : 'Best Fit',
          "Original Data Frequency": result.dataFrequency ?? (dataSummary ? dataSummary.dataFrequency : 'N/A'),
          "Rows in Original Dataset": dataSummary?.rowCount ?? 'N/A'
        };

        setDataSummary(newSummary);
        setShowSummary(true);
        
        showAlert(`Model ${selectedModels} execution completed successfully!`, "success");
      } else {
        showAlert(`Warning: ${result.message || "Unknown status returned from API"}`, "warning");
      }
    } catch (error) {
      showAlert(`Error running forecast model: ${error.message}`, "error");
      setIsLoading(false);
    }
  };

  useEffect(() => {
      const requiredFilled = parseInt(forecastHorizon, 10) > 0 && forecastLock && selectedDataset;
      // For 'Best Fit', check if at least one model is selected. For 'Select From List', check if one is chosen.
      const modelRequired = forecastMethod === "Select From List" 
        ? selectedModels.length === 1 
        : selectedModels.length > 0;
      setCanRunModel(requiredFilled && modelRequired);
  }, [selectedModels, forecastHorizon, forecastLock, selectedDataset, forecastMethod]);

  const handleDownloadForecast = async () => {
    try {
      if (!forecastResults) {
        showAlert("No forecast results available to download.", "error");
        return;
      }
      
      const exportData = {
        results: forecastResults.results,
        future_forecasts: forecastResults.future_forecasts,
        dates: forecastResults.dates,
        forecast_type: forecastResults.forecast_type || map_granularity_to_forecast_type(granularity),
        future_dates: forecastResults.future_dates
      };
      
      // If CSV data is already in the response, use that directly
      if (forecastResults.csv_data) {
        downloadCSV(forecastResults.csv_data);
        return;
      }
      const token = getAuthToken();
      if (!token) {
        console.error("No auth token found, stopping fetch.");
        return;
      }
      
      // Otherwise call the export endpoint
      const response = await fetch(`${BASE_URL}/export-forecast`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify(exportData)
      });
      
      if (!response.ok) {
        throw new Error(`Export failed with status ${response.status}`);
      }
      
      // Check if the response is JSON (error) or CSV (success)
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        // Handle error response
        const errorData = await response.json();
        throw new Error(errorData.message || "Export failed");
      }
      
      // Success - download the CSV
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      a.download = "forecast_results.csv";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading forecast:", error);
      showAlert(`Error downloading forecast: ${error.message}`, "error");
    }
  };
  
  // Helper function to map granularity to forecast_type
  const map_granularity_to_forecast_type = (granularity) => {
    const mapping = {
      "Overall": "Overall",
      "ProductID-wise": "Item-wise",
      "StoreID-ProductID Combination": "Store-Item Combination"
    };
    return mapping[granularity] || "Overall";
  };
  
  // Helper function to download CSV data directly
  const downloadCSV = (csvData) => {
    try {
      // Convert the data to CSV format
      let csvContent = "data:text/csv;charset=utf-8,";
      
      // Add headers
      if (csvData.length > 0) {
        const headers = Object.keys(csvData[0]);
        csvContent += headers.join(",") + "\n";
        
        // Add rows
        csvData.forEach(row => {
          const rowContent = headers.map(header => {
            // Handle values with commas
            const value = row[header] !== null && row[header] !== undefined ? row[header].toString() : "";
            return value.includes(",") ? `"${value}"` : value;
          }).join(",");
          csvContent += rowContent + "\n";
        });
      }
      
      // Create download link
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", "forecast_results.csv");
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error("Error creating CSV:", error);
      showAlert(`Error creating CSV: ${error.message}`, "error");
    }
  };

  const handleForecastHorizonChange = (e) => {
    const value = e.target.value;
    setForecastHorizon(value);
    // If forecast lock is greater than new horizon, reset it
    if (parseInt(forecastLock) > parseInt(value)) {
      setForecastLock("0");
    }
  };

  const handleForecastLockChange = (e) => {
    const value = e.target.value;
    const horizon = parseInt(forecastHorizon);
    const lock = parseInt(value);
    
    if (lock >= horizon) {
      showAlert("Forecast lock period must be less than forecast horizon", "error");
      return;
    }
    
    setForecastLock(value);
  };

  // Add organization calendar state
  const [organizationId, setOrganizationId] = useState('default');
  const [weekStartDay, setWeekStartDay] = useState(0); // 0=Monday
  const [organizationCalendars, setOrganizationCalendars] = useState([]);
  const [showCalendarConfig, setShowCalendarConfig] = useState(false);

  // Week day options for dropdown
  const weekDayOptions = [
    { value: 0, label: 'Monday' },
    { value: 1, label: 'Tuesday' },
    { value: 2, label: 'Wednesday' },
    { value: 3, label: 'Thursday' },
    { value: 4, label: 'Friday' },
    { value: 5, label: 'Saturday' },
    { value: 6, label: 'Sunday' }
  ];

  // Load organization calendars on component mount
  useEffect(() => {
    fetchOrganizationCalendars();
  }, []);

  const fetchOrganizationCalendars = async () => {
    try {
      const response = await fetch('/api/engine/organization/calendars', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setOrganizationCalendars(data.calendars || []);
      }
    } catch (error) {
      console.error('Error fetching organization calendars:', error);
    }
  };

  const saveOrganizationCalendar = async () => {
    try {
      const response = await fetch('/api/engine/organization/calendar', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          organization_id: organizationId,
          week_start_day: weekStartDay
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        alert(`Calendar configuration saved: Week starts on ${result.week_start_name} for organization ${organizationId}`);
        fetchOrganizationCalendars(); // Refresh the list
        setShowCalendarConfig(false);
      } else {
        const error = await response.json();
        alert(`Error: ${error.message}`);
      }
    } catch (error) {
      console.error('Error saving organization calendar:', error);
      alert('Error saving calendar configuration');
    }
  };

  const modelDropdownRef = useRef(null);
  useEffect(() => {
    const handleClickOutside = (event) => {
      // Check if the ref is initialized and if the click is outside the component
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(event.target)) {
        setIsModelDropdownOpen(false);
      }
    };
    // Add event listener
    document.addEventListener("mousedown", handleClickOutside);
    // Cleanup the event listener on component unmount
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <>
      <PageTitle title="Forecast Settings" />
      <div className="forecast-container">
        <style>{customStyles}</style>

        {/* Alert Component */}
        {alert.isOpen && (
          <div className="alert-overlay" style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.6)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
            backdropFilter: "blur(5px)"
          }}>
            <div className={`alert alert-${alert.type}`} style={{
              padding: "25px 30px",
              borderRadius: "12px",
              backgroundColor: "#ffffff",
              color: "#333333",
              border: "none",
              boxShadow: "0 10px 25px rgba(0, 0, 0, 0.1)",
              maxWidth: "450px",
              width: "90%",
              position: "relative",
              display: "flex",
              flexDirection: "column",
              gap: "15px",
              animation: "slideIn 0.3s ease-out"
            }}>
              <div style={{ 
                display: "flex", 
                alignItems: "flex-start",
                gap: "15px" 
              }}>
                {/* Alert Icon */}
                <div style={{
                  flexShrink: 0,
                  width: "24px",
                  height: "24px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRadius: "50%",
                  backgroundColor: alert.type === "error" ? "#FEE2E2" : 
                                alert.type === "success" ? "#DCFCE7" : 
                                alert.type === "warning" ? "#FEF9C3" : "#DBEAFE",
                  color: alert.type === "error" ? "#DC2626" : 
                        alert.type === "success" ? "#16A34A" : 
                        alert.type === "warning" ? "#CA8A04" : "#2563EB"
                }}>
                  {alert.type === "error" && (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M8 5.33333V8M8 10.6667H8.00667M14 8C14 11.3137 11.3137 14 8 14C4.68629 14 2 11.3137 2 8C2 4.68629 4.68629 2 8 2C11.3137 2 14 4.68629 14 8Z" 
                            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                  {alert.type === "success" && (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M13.3333 4L6 11.3333L2.66667 8" 
                            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                  {alert.type === "warning" && (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M8 5.33333V8M8 10.6667H8.00667M8 14C11.3137 14 14 11.3137 14 8C14 4.68629 11.3137 2 8 2C4.68629 2 2 4.68629 2 8C2 11.3137 4.68629 14 8 14Z" 
                            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                  {alert.type === "info" && (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <path d="M8 5.33333H8.00667M8 8V10.6667M8 14C11.3137 14 14 11.3137 14 8C14 4.68629 11.3137 2 8 2C4.68629 2 2 4.68629 2 8C2 11.3137 4.68629 14 8 14Z" 
                            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>

                {/* Alert Message */}
                <span style={{ 
                  flex: 1,
                  fontSize: "15px",
                  lineHeight: "1.5",
                  color: "#1F2937",
                  fontWeight: "500"
                }}>{alert.message}</span>

                {/* Close Button */}
                <button 
                  onClick={() => setAlert({...alert, isOpen: false})} 
                  style={{
                    background: "none",
                    border: "none",
                    fontSize: "20px",
                    cursor: "pointer",
                    color: "#9CA3AF",
                    padding: "0",
                    marginLeft: "10px",
                    marginTop: "-5px",
                    opacity: "0.7",
                    transition: "all 0.2s",
                    width: "24px",
                    height: "24px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: "6px",
                    ":hover": {
                      backgroundColor: "#F3F4F6",
                      opacity: "1",
                      color: "#4B5563"
                    }
                  }}
                >
                  ×
                </button>
              </div>

              {/* Progress Bar for Info/Loading alerts */}
              {alert.type === "info" && (
                <div style={{
                  width: "100%",
                  height: "2px",
                  backgroundColor: "#E5E7EB",
                  borderRadius: "1px",
                  overflow: "hidden",
                  marginTop: "5px"
                }}>
                  <div style={{
                    width: "100%",
                    height: "100%",
                    backgroundColor: "#60A5FA",
                    animation: "progress 2s linear infinite"
                  }}></div>
                </div>
              )}
            </div>
          </div>
        )}

        <style>
          {`
            @keyframes slideIn {
              from {
                opacity: 0;
                transform: translateY(-30px);
              }
              to {
                opacity: 1;
                transform: translateY(0);
              }
            }

            @keyframes progress {
              0% {
                transform: translateX(-100%);
              }
              100% {
                transform: translateX(100%);
              }
            }

            .alert-overlay {
              transition: all 0.3s ease-in-out;
            }

            .alert {
              transition: all 0.3s ease-in-out;
            }

            button:hover {
              background-color: #F3F4F6 !important;
              opacity: 1 !important;
              color: #4B5563 !important;
            }
          `}
        </style>

        <div className="forecast-methodology-section" style={{ marginBottom: "20px", marginTop: "20px" }}>
          <h4 style={{ fontSize: "18px", marginBottom: "10px" }}><strong>Forecast Methodology :</strong></h4>
          <div className="dropdown-container">
            <select 
              value={forecastMethod} 
              onChange={(e) => {
                setForecastMethod(e.target.value);
                if (e.target.value === "Best Fit") {
                  setSelectedModels(""); // Clear selected model when Best Fit is chosen
                }
              }} 
              className="centered-dropdown"
              style={{ minWidth: "200px" }}
            >
              <option value="Best Fit">Best Fit</option>
              <option value="Select From List">Select From List</option>
            </select>
          </div>
        </div>

        {/* Dataset Selection Dropdown */}
        <div className="forecast-details" style={{ marginBottom: "20px" }}>
          <label style={{ fontSize: "18px" }}><strong>Available Datasets :</strong></label>
          <select
            value={selectedDataset}
            onChange={handleDatasetChange}
            className="input-field"
            disabled={uploadedDatasets.length === 0}
          >
            <option value="">Select a Dataset</option>
            {uploadedDatasets.length > 0 && (
              <option key={0} value={uploadedDatasets[0]}>{uploadedDatasets[0]}</option>
            )}
          </select>
          {uploadedDatasets.length === 0 && (
            <p style={{ color: "#DC3545", fontSize: "14px", marginTop: "5px" }}>
              No file uploaded yet. Please upload data in the Import section.
            </p>
          )}
        </div>

        {/* Column Selection and Mapping */}
        {showColumns && Array.isArray(columnNames) && columnNames.length > 0 && (
          <div ref={columnSelectionRef} className="column-selection">
            <h3>Select and Map Columns</h3>

            <div className="available-columns">
              <h4>Available Columns:</h4>
              <div className="columns-container">
                {columnNames.map((col, index) => (
                  <div key={index} className="column-item">
                    {col}
                    <button className="delete-btn" onClick={() => handleDeleteColumn(col)}>
                      ✖
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {omittedColumns.length > 0 && (
              <div className="omitted-columns">
                <h4>Omitted Columns:</h4>
                <div className="columns-container">
                  {omittedColumns.map((col, index) => (
                    <div key={index} className="column-item">
                      {col.name}
                      <button className="retrieve-btn" onClick={() => handleRetrieveColumn(col.name)}>
                        ↺
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mapping-section">
              <h4>Map Mandatory Fields:</h4>
              <div className="mapping-container">
                {mandatoryFields.map((field) => (
                  <div key={field} className="mapping-item">
                    <label>{field}:</label>
                    <select
                      className="mapping-dropdown"
                      onChange={(e) => handleMappingChange(field, e.target.value)}
                      value={columnMappings[field] || ""}
                    >
                      <option value="">Select column...</option>
                      {Array.isArray(columnNames) && columnNames.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            <div className="time-dependent-variables">
              <h4>Select Additional Time-Dependent Variables:</h4>
              <div className="checkbox-container">
                {Array.isArray(columnNames) && columnNames.map((col) => (
                  <label key={col} className="checkbox-label">
                    <input
                      type="checkbox"
                      value={col}
                      checked={timeDependentVariables.includes(col)}
                      onChange={handleTimeDependentVariablesChange}
                    />
                    {col}
                  </label>
                ))}
              </div>
              <button className="clear-btn" onClick={handleClearTimeDependentVariables}>
                Clear Selection
              </button>
              <button
                className={`preview-btn ${!areMandatoryFieldsMapped() ? "disabled" : ""}`}
                onClick={handleShowPreview}
                style={{ marginLeft: "20px" }}
              >
                Show Preview
              </button>
            </div>
          </div>
        )}

        {/* --- Conditional Model Selection --- */}
        {/* 1. Shown for "Best Fit" */}
        {forecastMethod === "Best Fit" && (
          <div className="best-fit-options" style={{ marginTop: "20px" }}>
            {/* Best Fit Metric Dropdown */}
            <div className="forecast-details">
              <label style={{ fontSize: "18px" }}><strong>Best Fit Metric :</strong></label>
              <select value={bestFitMetric} onChange={(e) => setBestFitMetric(e.target.value)}>
                <option value="MAE">MAE (Mean Absolute Error)</option>
                <option value="MAPE">MAPE (Mean Absolute Percentage Error)</option>
                <option value="RMSE">RMSE (Root Mean Squared Error)</option>
                <option value="BIAS">BIAS</option>
              </select>
            </div>
            
            {/* Multi-select Model Checklist */}
            <div className="forecast-details" style={{ marginTop: "20px" }}>
              <label style={{ fontSize: "18px", display: "block", marginBottom: "5px" }}><strong>Models to Compare :</strong></label>
              <div className="multi-select-dropdown" ref={modelDropdownRef}>
                <div className="multi-select-selected" onClick={() => setIsModelDropdownOpen(!isModelDropdownOpen)}>
                  {selectedModels.length > 0 ? (
                    <div className="multi-select-pills">
                      {selectedModels.map(model => (
                        <span key={model} className="multi-select-pill">{model}</span>
                      ))}
                    </div>
                  ) : (
                    <span className="multi-select-placeholder">Select models...</span>
                  )}
                  <span>▼</span>
                </div>
                {isModelDropdownOpen && (
                  <div className="multi-select-options">
                    {isLoadingModels ? (<p style={{padding: '10px'}}>Loading...</p>) : (
                      models.map((modelName) => (
                        <div key={modelName} className="multi-select-option">
                          <input
                            type="checkbox"
                            id={`model-${modelName}`}
                            value={modelName}
                            checked={selectedModels.includes(modelName)}
                            onChange={(e) => {
                              const { value, checked } = e.target;
                              setSelectedModels((prev) =>
                                checked ? [...prev, value] : prev.filter((item) => item !== value)
                              );
                            }}
                          />
                          <label htmlFor={`model-${modelName}`} style={{width: '100%', cursor: 'pointer'}}>{modelName}</label>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 2. Shown for "Select From List" */}
        {forecastMethod === "Select From List" && (
          <div className="forecast-details">
            <label style={{ fontSize: "18px" }}><strong>Model Name :</strong></label>
            <select 
              value={selectedModels[0] || ""} 
              onChange={(e) => setSelectedModels(e.target.value ? [e.target.value] : [])} // Store as an array with one item
              disabled={isLoadingModels}
            >
              <option value="">Select a Model</option>
              {isLoadingModels ? (
                <option value="" disabled>Loading models...</option>
              ) : (
                models.map((model, index) => (
                  <option key={index} value={model}>
                    {model}
                  </option>
                ))
              )}
            </select>
          </div>
        )}

        {showColumns && (
            <div className="holiday-config-section">
                <h4>Holiday Configuration</h4>
                
                {/* Automatic Standard Holidays */}
                <div className="config-item">
                    <label>
                        <input
                            type="checkbox"
                            checked={useStandardHolidays}
                            onChange={(e) => setUseStandardHolidays(e.target.checked)}
                        />
                        Automatically include standard public holidays
                    </label>
                    {useStandardHolidays && (
                        <select
                            value={holidayCountry}
                            onChange={(e) => setHolidayCountry(e.target.value)}
                            style={{ marginLeft: '10px' }}
                        >
                            <option value="US">United States</option>
                            <option value="IN">India</option>
                            <option value="CA">Canada</option>
                        </select>
                    )}
                </div>
            </div>
        )}

        {/* Preview Table */}
        {showTable && Array.isArray(importedData) && importedData.length > 0 && Array.isArray(columnNames) && columnNames.length > 0 && (
          <div className="imported-data-table">
            <h3>Preview First 5 Rows</h3>
            <div className="preview-table-container">
              <table>
                <thead>
                  <tr>
                    {columnNames.map((col, index) => (
                      <th key={index} scope="col">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {importedData.slice(0, 5).map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {columnNames.map((col, colIndex) => (
                        <td key={colIndex}>
                          {row[col] || ""}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              ref={uploadButtonRef}
              className="upload-data-for-cleaning"
              onClick={handleUploadDataForCleaning}
            >
              Upload Data for Cleaning
            </button>
          </div>
        )}

        {/* Granularity Dropdown (Moved Here) */}
        {showTable && (
          <div className="granularity-section" style={{ marginTop: "20px" }}>
            <h4 style={{ fontSize: "18px" }}><strong>Granularity :</strong></h4>
            <div className="dropdown-container">
              <select
                value={granularity}
                onChange={(e) => setGranularity(e.target.value)}
                className="centered-dropdown"
              >
                {granularityOptions.map((option, index) => (
                  <option key={index} value={option}>{option}</option>
                ))}
              </select>
            </div>
          </div>
        )}
        
        <div className="top-buttons">
          <button className="reset-button" onClick={resetForm}>Reset</button>
        </div>

        <div className="time-settings">
          <h4 style={{ fontSize: "18px" }}><strong>Time Settings :</strong></h4>
          <div className="settings-card-group" style={{ display: "flex", gap: "10px" }}>
            
            <div className="settings-card" style={{ flex: "0.9" }}>
              <h5 style={{ fontSize: "16px" }}>Time Bucket</h5>
              <div className="input-group">
                <select style={{ width: "120px" }} value={timeBucket} onChange={(e) => setTimeBucket(e.target.value)}>
                  {(() => {
                    const freqHierarchy = { 'daily': 1, 'weekly': 2, 'monthly': 3, 'yearly': 5 };
                    const detectedLevel = freqHierarchy[detectedDataFrequency] || 1;

                    return [
                    <option key="Daily" value="Daily" disabled={freqHierarchy['daily'] < detectedLevel}>Daily</option>,
                    <option key="Weekly" value="Weekly" disabled={freqHierarchy['weekly'] < detectedLevel}>Weekly</option>,
                    <option key="Monthly" value="Monthly" disabled={freqHierarchy['monthly'] < detectedLevel}>Monthly</option>,
                    <option key="Yearly" value="Yearly" disabled={freqHierarchy['yearly'] < detectedLevel}>Yearly</option>
                  ];
                })()}
                </select>
              </div>
            </div>

            <div className="settings-card">
              <h5 style={{ fontSize: "16px" }}>Forecast Parameters</h5>
              <div className="input-group">
                <label>
                  Forecast Next {forecastHorizon || 'X'} {pluralTimeUnit}
                  <span 
                    className="tooltip" 
                    title={`The number of future periods to forecast. E.g., 4 with 'Weekly' time bucket means forecasting the next 4 weeks.`}
                    style={{ cursor: 'pointer', marginLeft: '5px', color: '#007bff' }}
                  >
                    ⓘ
                  </span>
                </label>
                <input 
                  type="number" 
                  value={forecastHorizon} 
                  onChange={handleForecastHorizonChange}
                  min="1"
                  placeholder="e.g., 12"
                />
              </div>
              <div className="input-group">
                <label>Forecast Lock Period:</label>
                <input 
                  type="number" 
                  value={forecastLock} 
                  onChange={handleForecastLockChange}
                  min="0"
                  max={parseInt(forecastHorizon) - 1}
                />
              </div>
            </div>
            
            <div className="settings-card">
              <h5 style={{ fontSize: "16px" }}>Organization Calendar</h5>
              <div className="input-group">
                <label>Organization:</label>
                <input 
                  type="text" 
                  value={organizationId} 
                  onChange={(e) => setOrganizationId(e.target.value)}
                  placeholder="Organization ID"
                  style={{ width: "120px" }}
                />
              </div>
              <div className="input-group">
                <button 
                  onClick={() => setShowCalendarConfig(!showCalendarConfig)}
                  style={{ 
                    padding: "5px 10px", 
                    backgroundColor: "#007bff", 
                    color: "white", 
                    border: "none", 
                    borderRadius: "4px",
                    cursor: "pointer",
                    fontSize: "12px"
                  }}
                >
                  {showCalendarConfig ? "Hide" : "Configure"} Calendar
                </button>
              </div>
            </div>
          </div>
          
          {/* Organization Calendar Configuration Panel */}
          {showCalendarConfig && (
            <div className="calendar-config-panel" style={{ 
              marginTop: "15px", 
              padding: "15px", 
              border: "1px solid #ddd", 
              borderRadius: "5px",
              backgroundColor: "#f9f9f9"
            }}>
              <h5 style={{ fontSize: "16px", marginBottom: "10px" }}>
                <strong>Calendar Configuration for {organizationId}</strong>
              </h5>
              
              <div style={{ display: "flex", gap: "15px", alignItems: "center" }}>
                <div className="input-group">
                  <label>Week starts on:</label>
                  <select 
                    value={weekStartDay} 
                    onChange={(e) => setWeekStartDay(parseInt(e.target.value))}
                    style={{ width: "120px" }}
                  >
                    {weekDayOptions.map(option => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                
                <button 
                  onClick={saveOrganizationCalendar}
                  style={{ 
                    padding: "8px 15px", 
                    backgroundColor: "#28a745", 
                    color: "white", 
                    border: "none", 
                    borderRadius: "4px",
                    cursor: "pointer"
                  }}
                >
                  Save Calendar
                </button>
              </div>
              
              {/* Display existing organization calendars */}
              {organizationCalendars.length > 0 && (
                <div style={{ marginTop: "15px" }}>
                  <h6 style={{ fontSize: "14px", marginBottom: "8px" }}>
                    <strong>Existing Organization Calendars:</strong>
                  </h6>
                  <div style={{ maxHeight: "100px", overflowY: "auto" }}>
                    {organizationCalendars.map((calendar, index) => (
                      <div key={index} style={{ 
                        fontSize: "12px", 
                        padding: "4px 8px", 
                        margin: "2px 0",
                        backgroundColor: "white",
                        border: "1px solid #eee",
                        borderRadius: "3px"
                      }}>
                        <strong>{calendar.organization_id}:</strong> Week starts on {calendar.week_start_name}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="forecast-parameters active">
          <h4 style={{ fontSize: "18px" }}><strong>Forecast Parameters :</strong></h4>
          <div className="forecast-methodology">
            <div className="dropdown-container">
              <label style={{ fontSize: "16px" }}><strong>Aggregation Level: </strong></label>
              <select value={aggregation} onChange={(e) => setAggregation(e.target.value)} className="centered-dropdown">
                <option value="Sum">Sum</option>
                <option value="Average">Average</option>
                <option value="Max">Max</option>
              </select>
            </div>
          </div>
        </div>

        {/* Run Model Button - Show for both Best Fit and Select From List */}
        {((forecastMethod === "Best Fit") || (forecastMethod === "Select From List" && selectedModels)) && selectedDataset && (
          <div className="run-model-card">
            <h4>Model Execution</h4>
            <button
              className={`run-button ${canRunModel ? "active" : "disabled"}`}
              onClick={handleRunModel}
              disabled={!canRunModel}
            >
              Run Forecasting Model
            </button>
            {!canRunModel && <p className="validation-message">Please fill all required parameters</p>}
          </div>
        )}

        {/* Add loading indicator */}
        {isLoading && (
          <div className="loading-overlay">
            <div className="loading-spinner"></div>
            <p>Processing data... Please wait</p>
          </div>
        )}
        
        {/* Add data summary section */}
        {showSummary && dataSummary && (
          <div className="data-summary">
            <h3>Data Processing Summary</h3>
            <button className="close-btn" onClick={() => setShowSummary(false)}>×</button>
            <div className="summary-content">
              {Object.entries(dataSummary).map(([key, value]) => (
                <div key={key} className="summary-item">
                  <strong>{key}:</strong> {typeof value === 'object' ? JSON.stringify(value) : value}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Forecast Results Section */}
        {showForecastResults && forecastResults && (
          <div className="forecast-results-section">
            <div className="forecast-results-header">
              <h3 className="forecast-results-title">Forecast Results</h3>
              <button
                className="download-button"
                onClick={handleDownloadForecast}
                disabled={!forecastResults}
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 16l-4-4h3V4h2v8h3l-4 4zm9-13h-6v2h4.5c.83 0 1.5.67 1.5 1.5v13c0 .83-.67 1.5-1.5 1.5h-13c-.83 0-1.5-.67-1.5-1.5v-13c0-.83.67-1.5 1.5-1.5H11V3H3v18h18V3z"/>
                </svg>
                Download CSV
              </button>
            </div>
            {skippedItems.length > 0 && (
              <div className="skipped-items-warning" style={{
                padding: '15px',
                margin: '0 0 20px 0',
                border: '1px solid #ffc107',
                backgroundColor: '#fff3cd',
                borderRadius: '8px',
                maxHeight: '200px',
                overflowY: 'auto'
              }}>
                <h5 style={{ marginTop: 0, color: '#856404' }}>
                  Warning: Some items were not forecasted due to insufficient data
                </h5>
                <ul style={{ paddingLeft: '20px', margin: 0, fontSize: '12px' }}>
                  {skippedItems.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="results-content">
              <h4>Model Performance</h4>
              {Object.entries(forecastResults.results).map(([modelName, metrics]) => (
                <div key={modelName} className="model-results">
                  <h5>{modelName}</h5>
                  {typeof metrics === 'string' ? (
                    <p className="error-message">{metrics}</p>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Training</th>
                          <th>Validation</th>
                          <th>Test</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>RMSE</td>
                          <td>{metrics.train && metrics.train[0] ? metrics.train[0].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.val && metrics.val[0] ? metrics.val[0].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.test && metrics.test[0] ? metrics.test[0].toFixed(2) : 'N/A'}</td>
                        </tr>
                        <tr>
                          <td>MAPE</td>
                          <td>{metrics.train && metrics.train[1] ? metrics.train[1].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.val && metrics.val[1] ? metrics.val[1].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.test && metrics.test[1] ? metrics.test[1].toFixed(2) : 'N/A'}</td>
                        </tr>
                        <tr>
                          <td>MAE</td>
                          <td>{metrics.train && metrics.train[2] ? metrics.train[2].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.val && metrics.val[2] ? metrics.val[2].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.test && metrics.test[2] ? metrics.test[2].toFixed(2) : 'N/A'}</td>
                        </tr>
                        <tr>
                          <td>Bias</td>
                          <td>{metrics.train && metrics.train[3] ? metrics.train[3].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.val && metrics.val[3] ? metrics.val[3].toFixed(2) : 'N/A'}</td>
                          <td>{metrics.test && metrics.test[3] ? metrics.test[3].toFixed(2) : 'N/A'}</td>
                        </tr>
                      </tbody>
                    </table>
                  )}
                </div>
              ))}
              {forecastResults.forecast_type === "Overall" && (
                <div className="table-container">
                  <h4>Forecast (Overall)</h4>
                  <table>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Model</th>
                        <th>Forecast</th>
                        <th>Run Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {forecastResults.csv_data?.map((row, index) => (
                        <tr key={index}>
                          <td>{row.Date}</td>
                          <td>{row.Model}</td>
                          <td>{typeof row.Forecast === 'number' ? row.Forecast.toFixed(2) : row.Forecast}</td>
                          <td>{row.RunType}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {forecastResults.forecast_type === "Item-wise" && (
                <ItemWiseTable csvData={forecastResults.csv_data} />
              )}

              {forecastResults.forecast_type === "Store-Item Combination" && (
                <StoreItemComboTable csvData={forecastResults.csv_data} />
              )}
              </div>
            </div>
        )}
      </div>
    </>
  );
};

export default ForecastSettings;