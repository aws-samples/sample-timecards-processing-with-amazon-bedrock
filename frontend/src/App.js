import React, { useState, useEffect } from 'react';
import { Upload, FileText, CheckCircle, XCircle, Clock, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import axios from 'axios';
import './App.css';

// Memoized markdown component for performance
const MemoizedMarkdown = React.memo(({ content }) => (
  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
));

// Format currency with proper decimal places and commas
const formatCurrency = (amount) => {
  if (amount === null || amount === undefined || isNaN(amount)) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number(amount));
};

function App() {
  const [samples, setSamples] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(20);
  const [viewMode, setViewMode] = useState('rendered');

  useEffect(() => {
    loadSamples();
  }, []);

  const loadSamples = async () => {
    try {
      const response = await axios.get('/api/samples');
      setSamples(response.data);
    } catch (err) {
      console.error('Error loading samples:', err);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  };

  const handleFileUpload = async (file) => {
    if (!file.name.match(/\.(xlsx|xls|xlsm)$/)) {
      setError('Please select an Excel file (.xlsx, .xls, or .xlsm)');
      return;
    }

    setProcessing(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      const resultData = response.data;
      console.log('Upload - Received data:', resultData);
      console.log('Upload - Daily entries count:', resultData.extracted_data?.daily_entries?.length || 0);
      console.log('Upload - Total timecards claimed:', resultData.extracted_data?.total_timecards || 0);
      if (resultData.extracted_data?.daily_entries?.length > 0) {
        console.log('Upload - First 3 entries:', resultData.extracted_data.daily_entries.slice(0, 3));
      }
      setResult(resultData);
      setCurrentPage(1);
      setViewMode('rendered');
    } catch (err) {
      setError(err.response?.data?.error || 'Error processing file');
    } finally {
      setProcessing(false);
    }
  };

  const processSample = async (filename) => {
    setProcessing(true);
    setError(null);
    setResult(null);

    try {
      const response = await axios.get(`/api/process-sample/${filename}`);
      const resultData = response.data;
      console.log('Sample - Received data:', resultData);
      console.log('Sample - Daily entries count:', resultData.extracted_data?.daily_entries?.length || 0);
      console.log('Sample - Total timecards claimed:', resultData.extracted_data?.total_timecards || 0);
      if (resultData.extracted_data?.daily_entries?.length > 0) {
        console.log('Sample - First 3 entries:', resultData.extracted_data.daily_entries.slice(0, 3));
      }
      setResult(resultData);
      setCurrentPage(1);
      setViewMode('rendered');
    } catch (err) {
      setError(err.response?.data?.error || 'Error processing sample');
    } finally {
      setProcessing(false);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'valid':
        return <CheckCircle className="status-icon valid" />;
      case 'invalid':
        return <XCircle className="status-icon invalid" />;
      case 'error':
        return <AlertTriangle className="status-icon error" />;
      default:
        return <Clock className="status-icon processing" />;
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <FileText className="logo" />
          <h1>Cast & Crew Timecard Processor</h1>
          <p>Automated Excel timecard processing with AI extraction</p>
        </div>
      </header>

      <main className="main-content">
        <div className="upload-section">
          <div
            className={`upload-zone ${dragActive ? 'drag-active' : ''}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <Upload className="upload-icon" />
            <h3>Upload Excel Timecard</h3>
            <p>Drag and drop your Excel file here, or click to browse</p>
            <input
              type="file"
              accept=".xlsx,.xls,.xlsm"
              onChange={handleFileSelect}
              className="file-input"
            />
            <button className="upload-button">Choose File</button>
          </div>
        </div>

        {samples.length > 0 && (
          <div className="samples-section">
            <h3>Sample Files</h3>
            <div className="samples-grid">
              {samples.map((sample) => (
                <button
                  key={sample}
                  className="sample-button"
                  onClick={() => processSample(sample)}
                  disabled={processing}
                >
                  <FileText className="sample-icon" />
                  <span>{sample}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {processing && (
          <div className="processing-indicator">
            <div className="spinner"></div>
            <p>Processing timecard...</p>
          </div>
        )}

        {error && (
          <div className="error-message">
            <XCircle className="error-icon" />
            <p>{error}</p>
          </div>
        )}

        {result && (
          <>
            <div className="result-section">
              <div className="result-header">
                {getStatusIcon(result.status)}
                <h3>Processing Result</h3>
                <span className={`status-badge ${result.status}`}>
                  {result.status.toUpperCase()}
                </span>
              </div>

            {result.extracted_data && (
              <div className="extracted-data">
                <h4>Extracted Information</h4>
                <div className="summary-stats">
                  <div className="stat-item">
                    <label>Total Employees:</label>
                    <span>{result.extracted_data.daily_entries ? (() => {
                      const entryFormat = result.extracted_data.daily_entries_format || ["employee", "date", "rate", "project", "department"];
                      const arrayToObject = (entryArray) => {
                        if (!Array.isArray(entryArray)) return entryArray;
                        const obj = {};
                        entryFormat.forEach((field, index) => {
                          if (index < entryArray.length) {
                            if (field === "employee") {
                              obj.employee_name = entryArray[index];
                              obj.employee = entryArray[index];
                            } else {
                              obj[field] = entryArray[index];
                            }
                          }
                        });
                        obj.wage = parseFloat(obj.rate) || 0;
                        return obj;
                      };
                      const uniqueEmployees = new Set();
                      result.extracted_data.daily_entries.forEach(entry => {
                        const entryObj = arrayToObject(entry);
                        if (entryObj.employee_name || entryObj.employee) {
                          uniqueEmployees.add(entryObj.employee_name || entryObj.employee);
                        }
                      });
                      return uniqueEmployees.size;
                    })() : 0}</span>
                  </div>
                  <div className="stat-item">
                    <label>Total Timecards:</label>
                    <span>{result.extracted_data.daily_entries?.length || 0}</span>
                  </div>
                  <div className="stat-item">
                    <label>Total Days:</label>
                    <span>{result.extracted_data.daily_entries?.length || 0}</span>
                  </div>
                  <div className="stat-item">
                    <label>Total Wage:</label>
                    <span>{result.extracted_data.daily_entries ? (() => {
                      const entryFormat = result.extracted_data.daily_entries_format || ["employee", "date", "rate", "project", "department"];
                      const arrayToObject = (entryArray) => {
                        if (!Array.isArray(entryArray)) return entryArray;
                        const obj = {};
                        entryFormat.forEach((field, index) => {
                          if (index < entryArray.length) {
                            if (field === "employee") {
                              obj.employee_name = entryArray[index];
                              obj.employee = entryArray[index];
                            } else {
                              obj[field] = entryArray[index];
                            }
                          }
                        });
                        obj.wage = parseFloat(obj.rate) || 0;
                        return obj;
                      };
                      let totalWage = 0;
                      result.extracted_data.daily_entries.forEach(entry => {
                        const entryObj = arrayToObject(entry);
                        totalWage += parseFloat(entryObj.rate) || 0;
                      });
                      return formatCurrency(totalWage);
                    })() : formatCurrency(0)}</span>
                  </div>
                </div>

                {/* Data Validation Warnings */}
                {result.extracted_data.daily_entries && result.extracted_data.daily_entries.length > 0 && (() => {
                  const entryFormat = result.extracted_data.daily_entries_format || ["employee", "date", "rate", "project", "department"];
                  const arrayToObject = (entryArray) => {
                    if (!Array.isArray(entryArray)) return entryArray;
                    const obj = {};
                    entryFormat.forEach((field, index) => {
                      if (index < entryArray.length) {
                        if (field === "employee") {
                          obj.employee_name = entryArray[index];
                          obj.employee = entryArray[index];
                        } else {
                          obj[field] = entryArray[index];
                        }
                      }
                    });
                    obj.wage = parseFloat(obj.rate) || 0;
                    return obj;
                  };
                  
                  const uniqueEmployees = new Set();
                  let frontendTotalDays = 0;
                  let frontendTotalWage = 0;
                  
                  result.extracted_data.daily_entries.forEach(entry => {
                    const entryObj = arrayToObject(entry);
                    if (entryObj.employee_name || entryObj.employee) {
                      uniqueEmployees.add(entryObj.employee_name || entryObj.employee);
                    }
                    frontendTotalDays += 1;
                    frontendTotalWage += parseFloat(entryObj.rate) || 0;
                  });
                  
                  const frontendEmployeeCount = uniqueEmployees.size;
                  const backendEmployeeCount = result.extracted_data.employee_count || 0;
                  const backendTotalDays = result.extracted_data.total_days || 0;
                  const backendTotalWage = result.extracted_data.total_wage || 0;
                  
                  const employeeCountMismatch = Math.abs(frontendEmployeeCount - backendEmployeeCount) > 0;
                  const daysMismatch = Math.abs(frontendTotalDays - backendTotalDays) > 0;
                  const wageMismatch = Math.abs(frontendTotalWage - backendTotalWage) > 1;
                  
                  const hasDiscrepancies = employeeCountMismatch || daysMismatch || wageMismatch;
                  
                  return hasDiscrepancies && (
                    <div className="validation-warnings">
                      <div className="warning-header">
                        <AlertTriangle size={20} />
                        <h4>Data Validation Warnings</h4>
                      </div>
                      <div className="warning-content">
                        {employeeCountMismatch && (
                          <div className="warning-item">
                            Employee count mismatch: Frontend calculated {frontendEmployeeCount}, Backend reported {backendEmployeeCount}
                          </div>
                        )}
                        {daysMismatch && (
                          <div className="warning-item">
                            Days count mismatch: Frontend calculated {frontendTotalDays}, Backend reported {backendTotalDays}
                          </div>
                        )}
                        {wageMismatch && (
                          <div className="warning-item">
                            Wage total mismatch: Frontend calculated {formatCurrency(frontendTotalWage)}, Backend reported {formatCurrency(backendTotalWage)}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {result.extracted_data.daily_entries && result.extracted_data.daily_entries.length > 0 && (() => {
                  const totalItems = result.extracted_data.daily_entries.length;
                  const totalPages = Math.ceil(totalItems / itemsPerPage);
                  const startIndex = (currentPage - 1) * itemsPerPage;
                  const endIndex = startIndex + itemsPerPage;
                  const currentItems = result.extracted_data.daily_entries.slice(startIndex, endIndex);
                  
                  // Get format for array entries
                  const entryFormat = result.extracted_data.daily_entries_format || ["employee", "date", "rate", "project", "department"];
                  
                  // Helper function to convert array entry to object
                  const arrayToObject = (entryArray) => {
                    if (!Array.isArray(entryArray)) return entryArray; // Already an object
                    
                    const obj = {};
                    entryFormat.forEach((field, index) => {
                      if (index < entryArray.length) {
                        if (field === "employee") {
                          obj.employee_name = entryArray[index];
                          obj.employee = entryArray[index];
                        } else {
                          obj[field] = entryArray[index];
                        }
                      }
                    });
                    
                    // For daily rate system, wage equals rate
                    obj.wage = parseFloat(obj.rate) || 0;
                    
                    return obj;
                  };
                  
                  // Calculate totals from frontend data (independent verification)
                  const uniqueEmployees = new Set();
                  let frontendTotalDays = 0;
                  let frontendTotalWage = 0;
                  
                  result.extracted_data.daily_entries.forEach(entry => {
                    const entryObj = arrayToObject(entry);
                    if (entryObj.employee_name || entryObj.employee) {
                      uniqueEmployees.add(entryObj.employee_name || entryObj.employee);
                    }
                    frontendTotalDays += 1; // Each entry is one day
                    frontendTotalWage += parseFloat(entryObj.rate) || 0;
                  });
                  
                  const frontendEmployeeCount = uniqueEmployees.size;
                  
                  // Backend totals for comparison
                  const backendEmployeeCount = result.extracted_data.employee_count || 0;
                  const backendTotalDays = result.extracted_data.total_days || 0;
                  const backendTotalWage = result.extracted_data.total_wage || 0;
                  
                  // Check for discrepancies
                  const employeeCountMismatch = Math.abs(frontendEmployeeCount - backendEmployeeCount) > 0;
                  const daysMismatch = Math.abs(frontendTotalDays - backendTotalDays) > 0;
                  const wageMismatch = Math.abs(frontendTotalWage - backendTotalWage) > 1; // Allow $1 rounding difference

                  return (
                    <div className="timecards-table">
                      <div className="table-header">
                        <h5>Timecard Entries</h5>
                        <div className="table-summary">
                          Total: {totalItems} entries
                        </div>
                      </div>
                      
                      <div className="table-container">
                        <table>
                          <thead className="sticky-header">
                            <tr>
                              <th>Employee</th>
                              <th>Date</th>
                              <th>Rate</th>
                              <th>Wage</th>
                              <th>Project</th>
                              <th>Department</th>
                            </tr>
                          </thead>
                          <tbody>
                            {currentItems.map((entry, index) => {
                              const entryObj = arrayToObject(entry);
                              return (
                                <tr key={startIndex + index}>
                                  <td>{entryObj.employee_name || entryObj.employee || 'N/A'}</td>
                                  <td>{entryObj.date || 'N/A'}</td>
                                  <td>{formatCurrency(entryObj.rate || 0)}</td>
                                  <td>{formatCurrency(entryObj.wage || 0)}</td>
                                  <td>{entryObj.project || 'N/A'}</td>
                                  <td>{entryObj.department || 'N/A'}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      
                      <div className="pagination sticky-pagination">
                          <button 
                            className="pagination-btn"
                            onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                            disabled={currentPage === 1}
                          >
                            <ChevronLeft size={16} />
                            Previous
                          </button>
                          
                          <div className="pagination-info">
                            Page {currentPage} of {totalPages} 
                            <span className="pagination-details">
                              (Showing {startIndex + 1}-{Math.min(endIndex, totalItems)} of {totalItems} entries)
                            </span>
                            <div className="pagination-totals">
                              Total: {frontendTotalDays} days | {formatCurrency(frontendTotalWage)}
                            </div>
                          </div>
                          
                          <button 
                            className="pagination-btn"
                            onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                            disabled={currentPage === totalPages}
                          >
                            Next
                            <ChevronRight size={16} />
                          </button>
                        </div>
                    </div>
                  );
                })()}
              </div>
            )}



            {result.markdown_preview && (
              <div className="markdown-preview">
                <h4>Document Preview</h4>
                <div className="markdown-tabs">
                  <button 
                    className={`tab-button ${viewMode !== 'raw' ? 'active' : ''}`}
                    onClick={() => setViewMode('rendered')}
                  >
                    Rendered
                  </button>
                  <button 
                    className={`tab-button ${viewMode === 'raw' ? 'active' : ''}`}
                    onClick={() => setViewMode('raw')}
                  >
                    Raw Markdown
                  </button>
                </div>
                <div className="markdown-container">
                  {viewMode === 'raw' ? (
                    <pre className="markdown-content">
                      <code>{result.markdown_preview}</code>
                    </pre>
                  ) : (
                    <div className="markdown-rendered">
                      <MemoizedMarkdown content={result.markdown_preview} />
                    </div>
                  )}
                </div>
              </div>
            )}

            </div>

            {result.validation && (
              <div className="validation-section">
                <h4>Federal Wage Compliance Validation</h4>
                
                <div className="compliance-summary">
                  <div className={`validation-result ${result.validation.validation_result?.toLowerCase()}`}>
                    <strong>Status:</strong> {result.validation.validation_result}
                  </div>
                  <div className="compliance-text">
                    {result.validation.compliance_summary}
                  </div>
                </div>

                {result.validation.pay_calculation && (
                  <div className="pay-calculation">
                    <h5>Pay Calculation</h5>
                    <div className="pay-grid">
                      <div className="pay-item">
                        <label>Regular Pay:</label>
                        <span>{formatCurrency(result.validation.pay_calculation.regular_pay)}</span>
                      </div>
                      <div className="pay-item">
                        <label>Overtime Pay:</label>
                        <span>{formatCurrency(result.validation.pay_calculation.overtime_pay)}</span>
                      </div>
                      <div className="pay-item total">
                        <label>Total Pay:</label>
                        <span>{formatCurrency(result.validation.pay_calculation.total_pay)}</span>
                      </div>
                      <div className="pay-item">
                        <label>Pay Type:</label>
                        <span>{result.validation.pay_calculation.pay_type}</span>
                      </div>
                    </div>
                  </div>
                )}

                {result.validation.federal_compliance && (
                  <div className="federal-compliance">
                    <h5>Federal Compliance Check</h5>
                    <div className="compliance-checks">
                      <div className={`check-item ${result.validation.federal_compliance.minimum_wage_met ? 'pass' : 'fail'}`}>
                        <span>Minimum Wage Met:</span>
                        <span>{result.validation.federal_compliance.minimum_wage_met ? 'Yes' : 'No'}</span>
                      </div>
                      <div className={`check-item ${result.validation.federal_compliance.overtime_calculated ? 'pass' : 'fail'}`}>
                        <span>Overtime Calculated:</span>
                        <span>{result.validation.federal_compliance.overtime_calculated ? 'Yes' : 'No'}</span>
                      </div>
                      <div className={`check-item ${result.validation.federal_compliance.hours_within_limit ? 'pass' : 'fail'}`}>
                        <span>Hours Within Limit:</span>
                        <span>{result.validation.federal_compliance.hours_within_limit ? 'Yes' : 'No'}</span>
                      </div>
                      <div className={`check-item ${result.validation.federal_compliance.salary_exempt_threshold_met ? 'pass' : 'fail'}`}>
                        <span>Salary Exempt Threshold:</span>
                        <span>{result.validation.federal_compliance.salary_exempt_threshold_met ? 'Yes' : 'No'}</span>
                      </div>
                    </div>
                  </div>
                )}

                {result.validation.validation_issues && result.validation.validation_issues.length > 0 && (
                  <div className="validation-issues">
                    <h5>Issues Found</h5>
                    <ul>
                      {result.validation.validation_issues.map((issue, index) => (
                        <li key={index} className="issue-item">{issue}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {result.validation.requires_human_review && (
                  <div className="human-review-alert">
                    <h5>Human Review Required</h5>
                    <p>This timecard has been flagged for manual review by HR.</p>
                  </div>
                )}

                {result.validation.next_actions && result.validation.next_actions.length > 0 && (
                  <div className="next-actions">
                    <h5>Recommended Actions</h5>
                    <ul>
                      {result.validation.next_actions.map((action, index) => (
                        <li key={index} className="action-item">{action.replace(/[🔍📋❌📧💰⏰✅]/g, '').trim()}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default App;