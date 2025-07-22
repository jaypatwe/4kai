import React, { useEffect, useMemo, useState, useRef } from "react";
import PageTitle from "./PageTitle";

// MUI Core & Theme
import { ThemeProvider, createTheme } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonGroup from "@mui/material/ButtonGroup";
import Dialog from "@mui/material/Dialog";
import FormControl from "@mui/material/FormControl";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { DeviceHub as ModelIcon } from "@mui/icons-material";

// MUI Icons
import CloseIcon from "@mui/icons-material/Close";
import DateRangeIcon from "@mui/icons-material/DateRange";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import PublicIcon from "@mui/icons-material/Public";
import CategoryIcon from "@mui/icons-material/Category";
import TodayIcon from "@mui/icons-material/Today";

// Lucide-react Icons
import { AlertCircle, BarChart3, Target, TrendingUp } from "lucide-react";

// Nivo Charts
import { ResponsiveBar } from "@nivo/bar";
import { ResponsiveHeatMap } from "@nivo/heatmap";
import { ResponsiveLine } from "@nivo/line";

// Recharts & Animation (For the new drill-down chart)
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, LineChart, Line,
} from "recharts";
import { FaChevronRight, FaHome } from "react-icons/fa";
import { motion, AnimatePresence } from "framer-motion";

// Other 3rd Party
import GaugeChart from "react-gauge-chart";
import Cookies from "js-cookie";

// App Config
import { DASHBOARD_ENDPOINT } from "./config";
import { parseISO, format, isAfter, isBefore, isEqual, subDays, subMonths, startOfYear } from 'date-fns';


// --- DRILL-DOWN CHART COMPONENT ---
function DrillDownErrorChart({ regionData, productData, timeSeriesData }) {
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);

  const theme = {
      text: "#232a39",
      highlight: "#1e40af",
  };

  const renderBreadcrumbs = () => (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 8, fontSize: 16, color: theme.text }}>
      <span style={{ cursor: "pointer", display: "flex", alignItems: "center", fontWeight: 600 }} onClick={() => { setSelectedRegion(null); setSelectedProduct(null); }}>
        <FaHome style={{ marginRight: 4 }} /> Regions
      </span>
      {selectedRegion && (
        <>
          <FaChevronRight size={12} />
          <span style={{ fontWeight: selectedProduct ? 400 : 600, color: selectedProduct ? theme.text : theme.highlight, cursor: selectedProduct ? "pointer" : "default" }} onClick={() => selectedProduct && setSelectedProduct(null)}>
            {selectedRegion}
          </span>
        </>
      )}
      {selectedProduct && (
        <>
          <FaChevronRight size={12} />
          <span style={{ fontWeight: 600, color: theme.highlight }}>
            {selectedProduct}
          </span>
        </>
      )}
    </div>
  );

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <Paper elevation={3} sx={{ padding: '8px 12px', fontSize: 14 }}>
          <strong>{label}</strong>
          <ul style={{ listStyle: "none", margin: 0, padding: '4px 0 0 0' }}>
            {payload.map((p, i) => (
              <li key={i} style={{ color: p.color, fontWeight: 500 }}>
                {p.name}: <span style={{ fontWeight: 700 }}>{p.value}</span>
              </li>
            ))}
          </ul>
        </Paper>
      );
    }
    return null;
  };

  return (
    <Box sx={{ p: { xs: 1, sm: 2 }, fontFamily: "Inter,sans-serif" }}>
       <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>Forecast Error Distribution</Typography>
      <AnimatePresence mode="wait">
        <motion.div
          key={selectedRegion + "_" + selectedProduct}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          transition={{ duration: 0.35 }}
        >
          {renderBreadcrumbs()}
          
          {!selectedRegion && (
            <Box>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={regionData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }} barCategoryGap="25%" onClick={(state) => state && state.activeLabel && setSelectedRegion(state.activeLabel)} style={{ cursor: "pointer" }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis type="number" />
                  <YAxis dataKey="region" type="category" width={50} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f5f5f5' }}/>
                  <Legend iconType="circle" />
                  <Bar dataKey="Overforecast" stackId="a" fill="#ef4444" radius={[0, 10, 10, 0]} />
                  <Bar dataKey="Underforecast" stackId="a" fill="#3b82f6" />
                  <Bar dataKey="Accurate" stackId="a" fill="#22c55e" radius={[0, 10, 10, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <Typography variant="caption" sx={{ mt: 1, display: 'block', textAlign: 'center', color: 'text.secondary' }}>Click a region to drill down.</Typography>
            </Box>
          )}

          {selectedRegion && !selectedProduct && (
            <Box>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={productData[selectedRegion]} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }} barCategoryGap="25%" onClick={(state) => state && state.activeLabel && setSelectedProduct(state.activeLabel)} style={{ cursor: "pointer" }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis type="number" />
                  <YAxis dataKey="product" type="category" width={70} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: '#f5f5f5' }} />
                  <Legend iconType="circle" />
                  <Bar dataKey="Overforecast" stackId="a" fill="#ef4444" radius={[0, 10, 10, 0]} />
                  <Bar dataKey="Underforecast" stackId="a" fill="#3b82f6" />
                  <Bar dataKey="Accurate" stackId="a" fill="#22c55e" radius={[0, 10, 10, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <Typography variant="caption" sx={{ mt: 1, display: 'block', textAlign: 'center', color: 'text.secondary' }}>Click a product to see its time series.</Typography>
            </Box>
          )}

          {selectedRegion && selectedProduct && (
            <Box>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={(timeSeriesData[selectedRegion] && timeSeriesData[selectedRegion][selectedProduct]) || []} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend iconType="circle" />
                  <Line type="monotone" dataKey="Overforecast" stroke="#ef4444" strokeWidth={2} activeDot={{ r: 8 }} />
                  <Line type="monotone" dataKey="Underforecast" stroke="#3b82f6" strokeWidth={2} activeDot={{ r: 8 }} />
                  <Line type="monotone" dataKey="Accurate" stroke="#22c55e" strokeWidth={2} activeDot={{ r: 8 }} />
                </LineChart>
              </ResponsiveContainer>
              <Typography variant="caption" sx={{ mt: 1, display: 'block', textAlign: 'center', color: 'text.secondary' }}>Use breadcrumbs to navigate back.</Typography>
            </Box>
          )}
        </motion.div>
      </AnimatePresence>
    </Box>
  );
}


function Dashboard({ children }) {
  return (
    <Box sx={{ width: '100%', minHeight: '100vh', bgcolor: '#ffffff', p: 3 }}>
      <Box sx={{ maxWidth: '1800px', margin: '0 auto', '& > * + *': { mt: 3 } }}>{children}</Box>
    </Box>
    
  );
}

// ChartCard with expand logic
function ChartCard({ title, children, onExpand }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Paper sx={{ p: 2, height: '100%', position: 'relative' }}>
        

        {onExpand && (
          <IconButton
            size="small"
            sx={{ position: 'absolute', top: 8, right: 8, zIndex: 2 }}
            onClick={onExpand}
            aria-label={`Expand ${title}`}
          >
            <OpenInFullIcon fontSize="small" />
          </IconButton>
        )}

        {children}
      </Paper>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <Box sx={{ position: 'relative', p: 2, bgcolor: 'background.paper' }}>
          <IconButton size="small" sx={{ position: 'absolute', top: 8, right: 8, zIndex: 2 }} onClick={() => setOpen(false)} aria-label={`Close ${title}`}>
            <CloseIcon fontSize="small" />
          </IconButton>
          <Box sx={{ p: 2, minHeight: 400, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{children}</Box>
        </Box>
      </Dialog>
    </>
  );
}

function ChartWrapper({ children }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      window.dispatchEvent(new Event("resize"));
    }, 100);
    return () => clearTimeout(timer);
  }, []);
  return children;
}

function ExpandDialog({ isOpen, onClose, title, children }) {
  return (
    <Dialog
      open={isOpen}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{ sx: { bgcolor: '#fff', borderRadius: 3, p: 0 } }}
    >
      <Box sx={{ p: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #e5e7eb' }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>{title}</Typography>
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </Box>
      <Box sx={{ p: 3, height: 500, minHeight: 400, overflow: 'auto' }}>
        {children}
      </Box>
    </Dialog>
  );
}



// FilterBar
function FilterBar({ filters, onFilterChange, productFamilies, models, regions, minDate, maxDate }) {
  const handleChange = (field) => (event) => {
    onFilterChange({ ...filters, [field]: event.target.value });
  };

  console.log("FilterBar rendering with props:", { minDate, maxDate, startDate: filters.startDate, endDate: filters.endDate });

  return (
    <Paper sx={{ p: 2, mb: 3, borderRadius: 2, boxShadow: '0 8px 12px rgba(0,0,0,0.05)' }}>
      <Grid container spacing={2} alignItems="center">
        {/* Region */}
        <Grid item xs={12} sm={3}>
          <FormControl fullWidth size="small">
            <InputLabel>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <PublicIcon fontSize="small" />
                Region
              </Box>
            </InputLabel>
            <Select value={filters.region} label="Region" onChange={handleChange('region')}>
              {regions.map(r => (
                <MenuItem key={r} value={r}>{r}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        {/* Product Family */}
        <Grid item xs={12} sm={3}>
          <FormControl fullWidth size="small">
            <InputLabel>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <CategoryIcon fontSize="small" />
                Product Family
              </Box>
            </InputLabel>
            <Select value={filters.productFamily} label="Product Family" onChange={handleChange('productFamily')}>
              {productFamilies.map(pf => (
                <MenuItem key={pf} value={pf}>{pf}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        {/* Model */}
        <Grid item xs={12} sm={3}>
          <FormControl fullWidth size="small">
            <InputLabel>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <ModelIcon fontSize="small" />
                Model
              </Box>
            </InputLabel>
            <Select value={filters.model} label="Model" onChange={handleChange('model')}>
              {models.map(m => (
                <MenuItem key={m} value={m}>{m}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        {/* Start Date */}
        <Grid item xs={12} sm={1.5}>
          <TextField
            fullWidth
            label="Start Date"
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            value={filters.startDate}
            inputProps={{ min: minDate, max: filters.endDate }}
            onChange={handleChange('startDate')}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <TodayIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
        </Grid>
        {/* End Date */}
        <Grid item xs={12} sm={1.5}>
          <TextField
            fullWidth
            label="End Date"
            type="date"
            size="small"
            InputLabelProps={{ shrink: true }}
            value={filters.endDate}
            inputProps={{ min: filters.startDate, max: maxDate }}
            onChange={handleChange('endDate')}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <TodayIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
        </Grid>
      </Grid>
    </Paper>
  );
}

// Chart Components
function ForecastActualTimeSeries({
  data = [],
  showTitle = true,
  startDate,
  endDate,
  activeRange,
  handleRangeClick
} = {}) {
  // Defensive sort (handles out-of-order data)
  const sortedData = useMemo(
    () => [...data].sort((a, b) => new Date(a.date) - new Date(b.date)),
    [data]
  );
  const allMinDate = sortedData.length ? sortedData[0].date : null;
  const allMaxDate = sortedData.length ? sortedData[sortedData.length - 1].date : null;

  // Button enable/disable logic based on ALL data, not filtered
  const getIsRangeEnabled = (range, dataOverride = sortedData) => {
    if (!dataOverride.length) return false;
    const minD = dataOverride[0].date;
    const maxD = dataOverride[dataOverride.length - 1].date;
    const availableDays = (parseISO(maxD) - parseISO(minD)) / (1000 * 60 * 60 * 24) + 1;
    switch (range) {
      case '5D': return availableDays >= 5;
      case '1M': return availableDays >= 28;
      case '3M': return availableDays >= 85;
      case '6M': return availableDays >= 170;
      case 'YTD': return true;
      case 'All': return true;
      default: return true;
    }
  };

  const chartData = [
    {
      id: "Actual",
      data: sortedData
        .filter(d => typeof d.actual === "number" && !isNaN(d.actual))
        .map(d => ({
          x: d.date,
          y: d.actual
        }))
    },
    {
      id: "Forecast",
      data: sortedData
        .filter(d => typeof d.forecast === "number" && !isNaN(d.forecast))
        .map(d => ({
          x: d.date,
          y: d.forecast
        }))
    }
  ];

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Time Series
        </Typography>
        <ButtonGroup variant="outlined" size="small">
          {['5D', '1M', '3M', '6M', 'YTD', 'All'].map((r) => (
            <Button
              key={r}
              onClick={() => getIsRangeEnabled(r) && handleRangeClick(r)}
              variant={activeRange === r ? 'contained' : 'outlined'}
              disabled={!getIsRangeEnabled(r, sortedData)}
              sx={{
                color: '#1e40af',
                borderColor: '#1e40af',
                '&.MuiButton-contained': {
                  backgroundColor: '#1e40af',
                  color: '#fff',
                },
              }}
            >
              {r}
            </Button>
          ))}
        </ButtonGroup>
      </Box>

      <Typography variant="body2" sx={{ color: "#555", mb: 1, textAlign: 'right' }}>
        Filtered: {startDate} to {endDate} | Data available: {allMinDate} to {allMaxDate}
      </Typography>

      <Box sx={{ height : 300,
        "& .nivo-legend text": {
          fontSize: 22,
          fontWeight: 700,
          letterSpacing: "0.2px"
        }
      }}>
        <ResponsiveLine
          data={chartData}
          tooltip={({ point }) => {
            const isActual = point.serieId === "Actual";
            const label = isActual ? "Historical" : "Forecast";
            const color = isActual ? "#1e40af" : "#10b981";
            const dateStr = format(new Date(point.data.x), "yyyy-MM-dd");
          return (
            <Box sx={{
              bgcolor: "#fff",
              border: `2px solid ${color}`,
              borderRadius: 2,
              px: 4,
              py: 2,
              minWidth: 220,
              boxShadow: 2
            }}>
              <Typography sx={{ fontWeight: 700, color, mb: 0.5 }}>
                {label}
              </Typography>
              <Typography sx={{ color: "#222" }}>
                Date: <strong>{dateStr}</strong>
              </Typography>
              <Typography sx={{ color: "#222" }}>
                Demand: <strong>{point.data.yFormatted}</strong>
              </Typography>
            </Box>
          );
        }}
          xScale={{
            type: 'time',
            format: '%Y-%m-%d',
            precision: 'day',
            useUTC: false
          }}
          yScale={{ type: 'linear', min: 'auto', max: 'auto' }}
          axisBottom={{
            format: '%Y-%m-%d',
            tickRotation: -45,
            legend: 'Date',
            legendOffset: 36,
            legendPosition: 'middle'
          }}
          axisLeft={{ legend: 'Demand' }}
          colors={({ id }) => id === "Actual" ? "#1e40af" : "#10b981"}
          enablePoints={true}
          pointSize={4}
          margin={{ top: 20, right: 20, bottom: 60, left: 50 }}
          useMesh={true}
          curve="monotoneX"
          legends={[
            {
              anchor: 'top-right',          // Move legend to top-right for clarity
              direction: 'row',
              justify: false,
              translateY: -25,              // Move up above the chart
              itemsSpacing: 18,
              itemDirection: 'left-to-right',
              itemWidth: 100,               // Each legend item width
              itemHeight: 22,               // Legend height
              symbolSize: 22,               // Larger swatch for better visibility
              symbolShape: "circle",
              itemTextColor: "#1e293b",     // Dark blue-gray, strong contrast
              effects: [
                {
                  on: 'hover',
                  style: {
                    itemTextColor: '#1e40af',   // Highlight text on hover
                    itemBackground: '#e0e7ef',
                  }
                }
              ]
            }
          ]}
        />
      </Box>
    </Box>
  );
}

function CorrelationHeatmap({ showTitle = true } ={}) {
  const data = [
    {
      id: 'Demand',
      data: [
        { x: 'Price', y: 0.82 },
        { x: 'Promotion', y: 0.65 },
        { x: 'Holiday', y: 0.45 },
        { x: 'Weather', y: 0.32 },
        { x: 'Inventory', y: 0.18 }
      ]
    },
    {
      id: 'Price',
      data: [
        { x: 'Price', y: 1.0 },
        { x: 'Promotion', y: 0.78 },
        { x: 'Holiday', y: 0.25 },
        { x: 'Weather', y: 0.12 },
        { x: 'Inventory', y: -0.35 }
      ]
    },
    {
      id: 'Promotion',
      data: [
        { x: 'Price', y: 0.78 },
        { x: 'Promotion', y: 1.0 },
        { x: 'Holiday', y: 0.42 },
        { x: 'Weather', y: 0.08 },
        { x: 'Inventory', y: -0.22 }
      ]
    }
  ];

  return (
    <>
    {showTitle && (
      <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
        Feature Correlation Heatmap
      </Typography> )}
      <Box sx={{ height: 320 }}>
        <ResponsiveHeatMap
          data={data}
          margin={{ top: 60, right: 90, bottom: 60, left: 90 }}
          valueFormat={(v) => `${(v * 100).toFixed(0)}%`} 
          axisTop={{
            orient: 'top',
            tickSize: 5,
            tickPadding: 5,
            tickRotation: -45,
            legend: '',
          }}
          axisLeft={{
            orient: 'left',
            tickSize: 5,
            tickPadding: 5,
            legend: '',
          }}
          colors={{
            type: 'diverging',
            scheme: 'red_yellow_blue',
            divergeAt: 0.5,
            minValue: -1,
            maxValue: 1,
          }}
          cellBorderWidth={1}
          cellBorderColor="#ffffff"
          labelTextColor={{
            from: 'color',
            modifiers: [['darker', 3]]
          }}
          animate={true}
          enableLabels={true}
          isInteractive={true}
        />
      </Box>
    </>
  );
}

function DemandVolatilityGauge({ showTitle = true } ={}) {
  const value = 0.65;
  return (
    <>
      <Typography variant="h6" gutterBottom>Demand Volatility Index</Typography>
      <div style={{ width: '100%', height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <GaugeChart id="demand-volatility-gauge" nrOfLevels={20} percent={value} colors={["#22c55e", "#f59e42", "#ef4444"]} arcWidth={0.3} textColor="#1f2937" needleColor="#2563eb" />
      </div>
      <Typography variant="subtitle1" align="center" sx={{ mt: 2, fontWeight: 600 }}>
        Current Volatility: {Math.round(value * 100)}%
      </Typography>
    </>
  );
}

function ProductSalesBreakdown({ showTitle = true, data =[], filters } ={}) {
  if (
    !filters || !filters.region || filters.region === "All Stores"
  ) {
    return (
      <Box sx={{ p: 3, textAlign: 'center', color: "#888" }}>
        <Typography variant="h6">
          Please select a specific Store to see the breakdown.
        </Typography>
      </Box>
    );
  }
  return (
    <>
      {showTitle && (
        <Typography variant="h6" gutterBottom>Product Sales vs Forecast</Typography>
      )}
      <Box sx={{ height: 320 }}>
        <ResponsiveBar
          data={data}
          keys={['sales', 'forecast']}
          indexBy="product"
          colors={({ id }) => id === "sales" ? "#2563eb" : "#10b981"}
          groupMode="stacked"
          axisLeft={{
            legend: 'Units',
            legendPosition: 'middle',
            legendOffset: -40,
          }}
          legends={[
            {
              dataFrom: 'keys',
              anchor: 'top-right',
              direction: 'row',
              translateY: -25,
              itemsSpacing: 10,
              itemWidth: 120,
              itemHeight: 20,
              symbolSize: 16,
              symbolShape: 'circle',
            }
          ]}
          tooltip={({ id, value, indexValue, color, data }) => (
            <Box sx={{
              bgcolor: "#fff",
              border: `2px solid ${color}`,
              borderRadius: 2,
              px: 2,
              py: 1,
              minWidth: 120,
              boxShadow: 2
            }}>
              <Typography sx={{ color: "#222", fontWeight: 700 }}>
                {indexValue}
              </Typography>
              <Typography sx={{ color, mt: 0.5 }}>
                {id === "sales" ? "Historical" : "Forecasted"}: <strong>{value}</strong>
              </Typography>
            </Box>
          )}
        />
      </Box>
    </>
  );
}

function ForecastAccuracyWaterfall({ data = [], showTitle = true } ={}) {
  const rawData = [
    { label: 'Total Forecast', value: 0 },
     ...data.map(d => ({ label: d.label, value: d.value })),
  ];

   rawData.push({ label: 'Net Variance', isTotal: true });

  let cumulative = 0;
  const chartData = rawData.map((d, i) => {
    const base = cumulative;
    const value = d.value || 0;
    if (!d.isTotal) cumulative += value;

    return {
      label: d.label,
      offset: d.isTotal ? 0 : value > 0 ? base : base + value,
      delta: d.isTotal ? cumulative : Math.abs(value),
      displayValue: d.isTotal ? `+${cumulative}` : value > 0 ? `+${value}` : `${value}`,
      color: d.isTotal ? '#cbd5e1' : value > 0 ? '#3b82f6' : '#60a5fa', // blue tones
    };
  });

  return (
    <>
      <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
        Forecast Accuracy Analysis
      </Typography>
      <Typography variant="body2" sx={{ mb: 2, color: '#6b7280' }}>
        Breakdown of forecast variance by product
      </Typography>
      <Box sx={{ height: 400 }}>
        <ResponsiveBar
          data={chartData}
          keys={['offset', 'delta']}
          indexBy="label"
          layout="vertical"
          margin={{ top: 20, right: 30, bottom: 80, left: 60 }}
          padding={0.3}
          groupMode="stacked"
          colors={({ id, data }) => {
            if (id === 'offset') return 'rgba(0,0,0,0)';
            return data.color;
          }}
          label={({ id, data }) => {
            if (id === 'delta') return data.displayValue;
            return '';
          }}
          enableLabel={true}
          labelTextColor="#fff"
          borderRadius={2}
          axisBottom={{
            tickRotation: -35,
          }}
          axisLeft={{
            legend: 'Units',
            legendPosition: 'middle',
            legendOffset: -40,
          }}
          tooltip={({ indexValue, value }) => (
            <div style={{ padding: '6px 9px', background: 'white', border: '1px solid #ccc' }}>
              <strong>{indexValue}</strong>: {value}
            </div>
          )}
        />
      </Box>
    </>
  );
}

// KPI Components
const formatNumber = (num) => {
  if (num === undefined || num === null || isNaN(num)) return "-";
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
};


// KPICard Component
const KPICard = ({ title, value, icon: Icon, trend, color = "blue" }) => {
  const colorMap = {
    blue: "#e8f0fe",
  };
  const borderColorMap = {
    blue: "#fffff",
  };
  return (
    <Box
      sx={{
        p: 3,
        borderRadius: 3,
        backgroundColor: colorMap[color] || colorMap.blue,
        border: `2px solid ${borderColorMap[color] || borderColorMap.blue}`,
        boxShadow: '0 2px 8px rgba(30,64,175,0.08)',
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "#1e40af", opacity: 0.8 }}>{title}</Typography>
          <Typography variant="h4" sx={{ fontWeight: 900, color: "#1976d2", mt: 0.5 }}>{value}</Typography>
          {trend !== undefined && (
            <Typography variant="body2" sx={{ color: trend > 0 ? "#059669" : "#ef4444", fontWeight: 700, mt: 0.5 }}>
              {trend > 0 ? "↗" : "↘"} {Math.abs(trend)}%
            </Typography>
          )}
        </Box>
        <Icon size={32} style={{ opacity: 0.7, color: "#1976d2" }} />
      </Box>
    </Box>
  );
};

function KPISection({ data }) {
  return (
    <Grid container spacing={2}>
      <Grid item xs={12} sm={6} md={2.4}>
        <KPICard
          title="Total Demand"
          value={formatNumber(Number(data.totalDemand.toFixed(2)))}
          icon={BarChart3}
          color="blue"
        />
      </Grid>
      
      <Grid item xs={12} sm={6} md={2.4}>
        <KPICard
          title="MAPE"
          value={`${data.mape}%`}
          icon={Target} 
          color="blue"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={2.4}>
        <KPICard
          title="MAE"
          value={data.mae}
          icon={AlertCircle}
          color="green"
        />
      </Grid>
      <Grid item xs={12} sm={6} md={2.4}>
        <KPICard
          title="Forecast Bias"
          value= {data.forecastBias !== undefined && data.forecastBias !== null ? data.forecastBias : "-"}
          icon={TrendingUp}
          color="orange"
        />
      </Grid>
      
      <Grid item xs={12} sm={6} md={2.4}>
        <KPICard
          title="Weighted MAPE"
          value={data.weightedMape !== undefined && data.weightedMape !== null ? data.weightedMape.toFixed(2) + "%" : "-"}
          icon={Target}
          color="green"
        />
      </Grid>
    </Grid>
  );
}

// Main App
const theme = createTheme({
  palette: {
    primary: { main: '#1e40af', light: '#3b82f6', dark: '#1e3a8a', contrastText: '#ffffff' },
    secondary: { main: '#3b82f6', light: '#60a5fa', dark: '#2563eb', contrastText: '#ffffff' },
    background: { default: '#f8fafc', paper: '#ffffff' },
    text: { primary: '#1f2937', secondary: '#4b5563' },
  },
  typography: { fontFamily: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'].join(','), h1: { fontWeight: 800 }, h2: { fontWeight: 800 }, h3: { fontWeight: 800 }, h4: { fontWeight: 800 }, h5: { fontWeight: 700 }, h6: { fontWeight: 700 }, subtitle1: { fontWeight: 600 }, subtitle2: { fontWeight: 600 }, body1: { fontWeight: 500 }, body2: { fontWeight: 500 }, button: { fontWeight: 600, textTransform: 'none' }, caption: { fontWeight: 500 }, overline: { fontWeight: 600 } },
  shape: { borderRadius: 8 },
});

function Dashboard1() {
  const [expandedChart, setExpandedChart] = useState(null);
  const [kpiData, setKpiData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [productFamilies, setProductFamilies] = useState([]);
  const [regions, setRegions] = useState([]);
  const [models, setModels] = useState([]);
  const [minDate, setMinDate] = useState('');
  const [maxDate, setMaxDate] = useState('');


  // The FULL dataset, never overwritten!
  const [fullTimeSeriesData, setFullTimeSeriesData] = useState([]);
  const [timeSeriesData, setTimeSeriesData] = useState([]);
  const [productSalesBreakdown, setProductSalesBreakdown] = useState([]);
  const [forecastVariance, setForecastVariance] = useState([]);
  const [drilldownData, setDrilldownData] = useState({ regionData: [], productData: {}, timeSeriesData: {} });


  // Only these filters can trigger date resets:
  const [filters, setFilters] = useState({
    model: '',
    region: '',
    productFamily: '',
    startDate: '',
    endDate: '',
  });
  const [activeRange, setActiveRange] = useState('All');

  useEffect(() => {
    const fetchInit = async () => {
      setLoading(true);
      try {
        const token = Cookies.get("authToken");
        const initialResponse = await fetch(DASHBOARD_ENDPOINT, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
        if (!initialResponse.ok) throw new Error("Failed to initial filter data");
        const initialData = await initialResponse.json();

        const storeList = initialData.filters.storeList || [];
        const productList = initialData.filters.productList || [];
        const modelList = initialData.filters.modelList || [];

        // 2. Determine the default store to load
        const defaultStore = storeList.length > 0 ? storeList[0] : 'All Stores';

        
        setRegions(['All Stores', ...storeList]);
        setProductFamilies(['All Products', ...productList]);
        setModels(modelList);

        const params = new URLSearchParams();
        if (defaultStore !== 'All Stores') {
          params.append("store", defaultStore);
        }
        
        const dataResponse = await fetch(`${DASHBOARD_ENDPOINT}?${params.toString()}`, {
          headers: { "Authorization": `Bearer ${token}` }
        });
        if (!dataResponse.ok) throw new Error("Failed to load dashboard data");
        const res = await dataResponse.json();

        setMinDate(res.filters.minDate || '');
        setMaxDate(res.filters.maxDate || '');
        
        setFullTimeSeriesData(res.timeseries || []);
        setKpiData({
          totalDemand: res.kpiData.total_demand,
          mape: res.kpiData.mape,
          mae: res.kpiData.mae,
          forecastBias: res.kpiData.forecast_bias,
          weightedMape: res.kpiData.weighted_mape,
        });

        setForecastVariance(res.forecastVariance || []);
        setDrilldownData(res.drilldownErrorData || { regionData: [], productData: {}, timeSeriesData: {} });
        
        setProductSalesBreakdown(res.productSalesBreakdown || []);

        // Only set start/end ONCE here, based on data, to avoid double fetches!
        if ((res.timeseries || []).length) {
          const defaultStore = storeList.length > 0 ? storeList[0] : 'All Stores';
          setFilters({
            productFamily: 'All Products',
            region: defaultStore,
            model: (res.filters.modelList && res.filters.modelList[0]) || '',
            startDate: res.timeseries[0].date,
            endDate: res.timeseries[res.timeseries.length - 1].date,
          });
        }
        setTimeSeriesData(res.timeseries || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchInit();
    // eslint-disable-next-line
  }, []);

  // --- Date reset only on region/productFamily change ---
  const lastCoreFilters = useRef({ productFamily: '', region: '' });
  useEffect(() => {
    // Only do this if region/productFamily changed
    const coreFiltersChanged =
      filters.productFamily !== lastCoreFilters.current.productFamily ||
      filters.region !== lastCoreFilters.current.region;

    if (coreFiltersChanged && fullTimeSeriesData.length) {
      setFilters((f) => ({
        ...f,
        startDate: fullTimeSeriesData[0].date,
        endDate: fullTimeSeriesData[fullTimeSeriesData.length - 1].date,
      }));
      setActiveRange("All");
      lastCoreFilters.current = {
        productFamily: filters.productFamily,
        region: filters.region,
      };
    }
  }, [filters.productFamily, filters.region, fullTimeSeriesData]);

  // --- Time Series display update ---
  useEffect(() => {
    if (!filters.startDate || !filters.endDate || !fullTimeSeriesData.length) {
      setTimeSeriesData(fullTimeSeriesData);
      return;
    }
    setTimeSeriesData(
      fullTimeSeriesData.filter(
        d =>
          (isAfter(parseISO(d.date), filters.startDate) || isEqual(parseISO(d.date), filters.startDate)) &&
          (isBefore(parseISO(d.date), filters.endDate) || isEqual(parseISO(d.date), filters.endDate))
      )
    );
  }, [filters.startDate, filters.endDate, fullTimeSeriesData]);

  // --- Only KPIs/API (never time series) fetched on any filter change ---
  useEffect(() => {
    // No fetch on initial mount (empty filters)
    if (!filters.productFamily && !filters.region && !filters.model) return;
    const fetchDashboardData = async () => {
      setLoading(true);
      setError(null);
      try {
        const token = Cookies.get("authToken");
        const params = new URLSearchParams();
        if (filters.region && filters.region !== "All Stores") params.append("store", filters.region);
        if (filters.productFamily && filters.productFamily !== "All Products") params.append("product", filters.productFamily);
        if (filters.model) params.append("model", filters.model);
        if (filters.startDate) params.append("start", filters.startDate);
        if (filters.endDate) params.append("end", filters.endDate);

        const response = await fetch(`${DASHBOARD_ENDPOINT}?${params.toString()}`, {
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });
        if (!response.ok) throw new Error("Failed to load dashboard data");
        const res = await response.json();

        setKpiData({
          totalDemand: res.kpiData.total_demand,
          mape: res.kpiData.mape,
          mae: res.kpiData.mae,
          forecastBias: res.kpiData.forecast_bias,
          weightedMape: res.kpiData.weighted_mape,
        });
        // NEVER update timeSeriesData or filters here!
      } catch (err) {
        setError(err.message);
        setKpiData(null);
        setTimeSeriesData([]);
      } finally {
        setLoading(false);
      }
    };
    fetchDashboardData();
    // eslint-disable-next-line
  }, [filters.model, filters.region, filters.productFamily, filters.startDate, filters.endDate]);

  // Product-sales breakdown chart
  useEffect(() => {
    // This hook now triggers whenever the user changes the store filter.
    if (filters.region && filters.region !== "All Stores") {
      const fetchProductSalesBreakdown = async () => {
        try {
          const token = Cookies.get("authToken");
          const params = new URLSearchParams();
          params.append("store", filters.region);
          // We don't add product, so the backend gives us all products for the store
          if (filters.startDate) params.append("start", filters.startDate);
          if (filters.endDate) params.append("end", filters.endDate);

          const response = await fetch(
            `${DASHBOARD_ENDPOINT}?${params.toString()}`,
            {
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
              },
            }
          );
          if (!response.ok) throw new Error("Failed to load product sales breakdown");
          const res = await response.json();
          setProductSalesBreakdown(res.productSalesBreakdown || []);
        } catch (err) {
          console.error("Error fetching breakdown data:", err);
          setProductSalesBreakdown([]);
        }
      };
      
      // Only fetch if the dashboard is not in its initial loading state.
      // The initial data is already set by the fetchInit hook.
      if(!loading) {
        fetchProductSalesBreakdown();
      }
    } else {
      // If user selects "All Stores", clear the chart.
      setProductSalesBreakdown([]);
    }
  // This now only depends on the store filter, dates, and loading state.
  }, [filters.region, filters.startDate, filters.endDate, loading]);

  // --- Date Range quick-select handler ---
  const handleRangeClick = (range) => {
    if (!fullTimeSeriesData.length) return;
    const minDate = fullTimeSeriesData[0].date;
    const maxDate = fullTimeSeriesData[fullTimeSeriesData.length - 1].date;
    let end = maxDate;
    let start = minDate;
    switch (range) {
      case "5D":
        start = format(
          parseISO(maxDate) > parseISO(minDate)
            ? subDays(parseISO(maxDate), 4)
            : parseISO(minDate),
          "yyyy-MM-dd"
        );
        if (parseISO(start) < parseISO(minDate)) start = minDate;
        break;
      case "1M":
        start = format(subMonths(parseISO(maxDate), 1), "yyyy-MM-dd");
        if (parseISO(start) < parseISO(minDate)) start = minDate;
        break;
      case "3M":
        start = format(subMonths(parseISO(maxDate), 3), "yyyy-MM-dd");
        if (parseISO(start) < parseISO(minDate)) start = minDate;
        break;
      case "6M":
        start = format(subMonths(parseISO(maxDate), 6), "yyyy-MM-dd");
        if (parseISO(start) < parseISO(minDate)) start = minDate;
        break;
      case "YTD":
        start = format(startOfYear(parseISO(maxDate)), "yyyy-MM-dd");
        if (parseISO(start) < parseISO(minDate)) start = minDate;
        break;
      case "All":
      default:
        start = minDate;
        break;
    }
    setFilters((f) => ({ ...f, startDate: start, endDate: end }));
    setActiveRange(range);
  };

  // (OPTIONAL: Debug logging)
  useEffect(() => {
    // Uncomment if you want to watch filter changes
    // console.log("Filters updated:", filters);
  }, [filters]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Dashboard>
        <PageTitle title="Dashboard" />
        <FilterBar
          filters={filters}
          onFilterChange={setFilters}
          productFamilies={productFamilies}
          regions={regions}
          models={models}
          minDate={minDate}
          maxDate={maxDate}
        />
        <Box sx={{ mt: 3, px: 2 }}>
          {/* KPI Section */}
          <Box sx={{ mb: 3 }}>
            {kpiData ? <KPISection data={kpiData} /> : <div>Loading KPIs...</div>}
          </Box>
          {/* Time Series Chart */}
          <Box sx={{ mt: 4, mb: 2 }}>
            <ChartCard title="Time Series" onExpand={() => setExpandedChart('timeseries')}>
              <ForecastActualTimeSeries
                data={timeSeriesData}
                showTitle={true}
                startDate={filters.startDate}
                endDate={filters.endDate}
                activeRange={activeRange}
                handleRangeClick={handleRangeClick}
              />
            </ChartCard>
          </Box>
          {/* Dashboard Charts in Grid */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            
            <Grid item xs={12} md={6}>
              <ChartCard title="Product Sales vs Forecast" onExpand={() => setExpandedChart('prodforecast')}>
                <ProductSalesBreakdown data={productSalesBreakdown} filters={filters} />
              </ChartCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <ChartCard title="Forecast Accuracy Analysis" onExpand={() => setExpandedChart('FAAnalysis')}>
                <ForecastAccuracyWaterfall data={forecastVariance} />
              </ChartCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <ChartCard title="Feature Correlation Heatmap" onExpand={() => setExpandedChart('correlation')}>
                <CorrelationHeatmap />
              </ChartCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <ChartCard title="Forecast Error Drilldown" onExpand={() => setExpandedChart('drilldown')}>
                <DrillDownErrorChart
                  regionData={drilldownData.regionData}
                  productData={drilldownData.productData}
                  timeSeriesData={drilldownData.timeSeriesData}
                />
              </ChartCard>
            </Grid>
          </Grid>
          <ExpandDialog
            isOpen={!!expandedChart}
            onClose={() => setExpandedChart(null)}
            title={
              expandedChart === 'timeseries' ? 'Forecast vs Actual - Expanded View'
                : expandedChart === 'correlation' ? 'Feature Correlation - Expanded View'
                  : expandedChart === 'drilldown' ? 'Forecast Error Drilldown - Expanded View'
                    : expandedChart === 'DVIndex' ? 'Demand Volatility Index - Expanded View'
                      : expandedChart === 'prodforecast' ? 'Product Sales vs Forecast - Expanded View'
                        : expandedChart === 'FAAnalysis' ? 'Forecast Accuracy Analysis - Expanded View'
                          : ''
            }
          >
            {expandedChart === 'timeseries' && (
              <ChartWrapper>
                <ForecastActualTimeSeries
                  showTitle={false}
                  data={timeSeriesData}
                  startDate={filters.startDate}
                  endDate={filters.endDate}
                  activeRange={activeRange}
                  handleRangeClick={handleRangeClick}
                />
              </ChartWrapper>
            )}
            {expandedChart === 'correlation' && (
              <ChartWrapper>
                <CorrelationHeatmap showTitle={false} />
              </ChartWrapper>
            )}
            {expandedChart === 'drilldown' && (
              <ChartWrapper>
                <DrillDownErrorChart
                  regionData={drilldownData.regionData}
                  productData={drilldownData.productData}
                  timeSeriesData={drilldownData.timeSeriesData}
                />
              </ChartWrapper>
            )}
            {expandedChart === 'DVIndex' && <DemandVolatilityGauge />}
            {expandedChart === 'prodforecast' && <ProductSalesBreakdown />}
            {expandedChart === 'FAAnalysis' && <ForecastAccuracyWaterfall />}
          </ExpandDialog>
        </Box>
      </Dashboard>
    </ThemeProvider>
  );
}


export default Dashboard1;