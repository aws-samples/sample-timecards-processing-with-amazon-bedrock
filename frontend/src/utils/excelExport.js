import * as XLSX from 'xlsx';

// Configure XLSX for security - disable dangerous features
XLSX.set_fs(() => {
  throw new Error("File system access disabled for security");
});

// Safe XLSX configuration
const SAFE_XLSX_OPTIONS = {
  cellFormula: false,  // Disable formula parsing
  cellHTML: false,     // Disable HTML parsing
  cellNF: false,       // Disable number format parsing
  cellStyles: false,   // Disable style parsing
  sheetStubs: false,   // Disable stub cells
  bookDeps: false,     // Disable dependency parsing
  bookFiles: false,    // Disable file parsing
  bookProps: false,    // Disable property parsing
  bookSheets: false,   // Disable sheet parsing
  bookVBA: false,      // Disable VBA parsing
  password: "",        // No password support
  WTF: false          // Disable "What The Format" mode
};

/**
 * Export timecard entries to Excel file
 * @param {Array} entries - Array of timecard entries
 * @param {string} fileName - Name of the file to download
 * @param {Object} jobInfo - Additional job information to include
 */
export const exportTimecardEntriesToExcel = (entries, fileName = 'timecard_entries', jobInfo = {}) => {
  try {
    // Create a new workbook
    const workbook = XLSX.utils.book_new();

    // Prepare data for Excel
    const excelData = entries.map((entry, index) => ({
      'Entry #': index + 1,
      'Employee': entry.employee || entry[0] || 'N/A',
      'Date': entry.date || entry[1] || 'N/A',
      'Daily Rate': entry.rate || entry[2] || 0,
      'Project': entry.project || entry[3] || 'N/A',
      'Department': entry.department || entry[4] || 'N/A'
    }));

    // Create worksheet from data
    const worksheet = XLSX.utils.json_to_sheet(excelData);

    // Set column widths
    const columnWidths = [
      { wch: 10 }, // Entry #
      { wch: 20 }, // Employee
      { wch: 12 }, // Date
      { wch: 12 }, // Daily Rate
      { wch: 15 }, // Project
      { wch: 15 }  // Department
    ];
    worksheet['!cols'] = columnWidths;

    // Add the worksheet to workbook
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Timecard Entries');

    // Add summary sheet if job info is provided
    if (jobInfo && Object.keys(jobInfo).length > 0) {
      const summaryData = [
        { 'Property': 'Job ID', 'Value': jobInfo.id || 'N/A' },
        { 'Property': 'File Name', 'Value': jobInfo.file_name || 'N/A' },
        { 'Property': 'Status', 'Value': jobInfo.status || 'N/A' },
        { 'Property': 'Created At', 'Value': jobInfo.created_at || 'N/A' },
        { 'Property': 'Completed At', 'Value': jobInfo.completed_at || 'N/A' },
        { 'Property': 'Total Entries', 'Value': entries.length },
        { 'Property': 'Total Daily Rate Sum', 'Value': entries.reduce((sum, entry) => sum + (entry.rate || entry[2] || 0), 0).toFixed(2) }
      ];

      const summaryWorksheet = XLSX.utils.json_to_sheet(summaryData);
      summaryWorksheet['!cols'] = [{ wch: 20 }, { wch: 30 }];
      XLSX.utils.book_append_sheet(workbook, summaryWorksheet, 'Summary');
    }

    // Generate file name with timestamp
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const fullFileName = `${fileName}_${timestamp}.xlsx`;

    // Write and download the file with safe options
    XLSX.writeFile(workbook, fullFileName, SAFE_XLSX_OPTIONS);

    return {
      success: true,
      fileName: fullFileName,
      entriesCount: entries.length
    };
  } catch (error) {
    console.error('Error exporting to Excel:', error);
    return {
      success: false,
      error: error.message
    };
  }
};

/**
 * Export job results summary to Excel
 * @param {Object} jobResult - Complete job result object
 * @param {string} fileName - Name of the file to download
 */
export const exportJobResultToExcel = (jobResult, fileName = 'job_result') => {
  try {
    const workbook = XLSX.utils.book_new();

    // Extract different sections of the job result
    const { extracted_data, validation, processing_metadata } = jobResult;

    // 1. Timecard Entries Sheet
    if (extracted_data?.daily_entries) {
      const entries = extracted_data.daily_entries.map((entry, index) => ({
        'Entry #': index + 1,
        'Employee': entry[0] || 'N/A',
        'Date': entry[1] || 'N/A',
        'Daily Rate': entry[2] || 0,
        'Project': entry[3] || 'N/A',
        'Department': entry[4] || 'N/A'
      }));

      const entriesSheet = XLSX.utils.json_to_sheet(entries);
      entriesSheet['!cols'] = [
        { wch: 10 }, { wch: 20 }, { wch: 12 }, 
        { wch: 12 }, { wch: 15 }, { wch: 15 }
      ];
      XLSX.utils.book_append_sheet(workbook, entriesSheet, 'Timecard Entries');
    }

    // 2. Summary Sheet
    const summaryData = [];
    if (extracted_data) {
      summaryData.push(
        { 'Category': 'Basic Info', 'Property': 'Employee Name', 'Value': extracted_data.employee_name || 'N/A' },
        { 'Category': 'Basic Info', 'Property': 'Total Days', 'Value': extracted_data.total_days || 0 },
        { 'Category': 'Basic Info', 'Property': 'Unique Days', 'Value': extracted_data.unique_days || 0 },
        { 'Category': 'Financial', 'Property': 'Total Wage', 'Value': extracted_data.total_wage || 0 },
        { 'Category': 'Financial', 'Property': 'Average Daily Rate', 'Value': extracted_data.average_daily_rate || 0 }
      );
    }

    if (validation) {
      summaryData.push(
        { 'Category': 'Validation', 'Property': 'Validation Result', 'Value': validation.validation_result || 'N/A' },
        { 'Category': 'Validation', 'Property': 'Requires Human Review', 'Value': validation.requires_human_review ? 'Yes' : 'No' },
        { 'Category': 'Validation', 'Property': 'Issues Count', 'Value': validation.validation_issues?.length || 0 }
      );
    }

    if (processing_metadata) {
      summaryData.push(
        { 'Category': 'Processing', 'Property': 'Processing Time', 'Value': processing_metadata.processing_time_seconds || 'N/A' },
        { 'Category': 'Processing', 'Property': 'Model Used', 'Value': processing_metadata.model_used || 'N/A' }
      );
    }

    const summarySheet = XLSX.utils.json_to_sheet(summaryData);
    summarySheet['!cols'] = [{ wch: 15 }, { wch: 25 }, { wch: 20 }];
    XLSX.utils.book_append_sheet(workbook, summarySheet, 'Summary');

    // 3. Validation Issues Sheet (if any)
    if (validation?.validation_issues && validation.validation_issues.length > 0) {
      const issuesData = validation.validation_issues.map((issue, index) => ({
        'Issue #': index + 1,
        'Issue': issue
      }));

      const issuesSheet = XLSX.utils.json_to_sheet(issuesData);
      issuesSheet['!cols'] = [{ wch: 10 }, { wch: 60 }];
      XLSX.utils.book_append_sheet(workbook, issuesSheet, 'Validation Issues');
    }

    // Generate file name with timestamp
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    const fullFileName = `${fileName}_${timestamp}.xlsx`;

    // Write and download the file with safe options
    XLSX.writeFile(workbook, fullFileName, SAFE_XLSX_OPTIONS);

    return {
      success: true,
      fileName: fullFileName
    };
  } catch (error) {
    console.error('Error exporting job result to Excel:', error);
    return {
      success: false,
      error: error.message
    };
  }
};