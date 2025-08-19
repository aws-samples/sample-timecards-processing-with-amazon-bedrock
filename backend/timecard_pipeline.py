#!/usr/bin/env python3
"""
Cast & Crew Timecard Processing Pipeline
3-Step Process: Excel → Markdown → LLM Extraction → Automated Reasoning Validation
"""

import pandas as pd
import json
import boto3
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ValidationResult(Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    SATISFIABLE = "SATISFIABLE"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    TOO_COMPLEX = "TOO_COMPLEX"


@dataclass
class WageCompliance:
    """Federal wage compliance rules for entertainment industry"""

    federal_minimum_wage: float = 7.25
    overtime_threshold: int = 40  # hours per week
    overtime_multiplier: float = 1.5
    max_weekly_hours: int = 60  # requires approval beyond this
    salary_exempt_threshold: float = 684.0  # weekly salary threshold


class TimecardPipeline:
    def __init__(self, config_manager=None):
        self.config = config_manager

        # Initialize AWS clients with configuration and extended timeout
        region = self.config.aws_region if self.config else "us-west-2"

        # Configure boto3 with extended timeout for large requests
        from botocore.config import Config

        boto_config = Config(
            read_timeout=600,  # 10 minutes
            connect_timeout=60,  # 1 minute
            retries={"max_attempts": 1},
        )

        self.bedrock = boto3.client(
            "bedrock-runtime", region_name=region, config=boto_config
        )
        self.guardrails = boto3.client(
            "bedrock", region_name=region, config=boto_config
        )

        # Auto-provision Automated Reasoning if needed
        self._ensure_automated_reasoning_ready()

        # Initialize compliance rules from configuration
        if self.config:
            self.compliance = WageCompliance(
                federal_minimum_wage=self.config.federal_minimum_wage,
                overtime_threshold=self.config.overtime_threshold_hours,
                max_weekly_hours=self.config.max_recommended_hours_weekly,
                salary_exempt_threshold=self.config.salary_exempt_threshold_weekly,
            )
        else:
            self.compliance = WageCompliance()

        self.review_queue = []

    def _ensure_automated_reasoning_ready(self):
        """Ensure Automated Reasoning is provisioned (non-blocking)"""
        try:
            from automated_reasoning_provisioner import auto_provision_if_needed

            logger.info("Checking Automated Reasoning configuration...")

            # Non-blocking check/provision
            result = auto_provision_if_needed(
                config_manager=self.config,
                region_name=self.config.aws_region if self.config else "us-west-2",
            )

            status = result.get("status", "unknown")
            policy_arn = result.get("policy_arn")
            guardrail_id = result.get("guardrail_id")

            if status == "ready":
                logger.info("Automated Reasoning is READY")
                logger.info(f"   Policy ARN: {policy_arn}")
                logger.info(f"   Guardrail ID: {guardrail_id}")
                logger.info("   Mathematical validation will use formal logic")
            elif status == "creating":
                logger.info("Automated Reasoning setup IN PROGRESS")
                logger.info(f"   Policy ARN: {policy_arn}")
                logger.info(
                    f"   Status: {result.get('message', 'Creation in progress')}"
                )
                logger.info("   Using fallback validation until ready")
            elif status == "failed":
                logger.warning("Automated Reasoning setup FAILED")
                logger.warning(f"   Error: {result.get('error', 'Unknown error')}")
                logger.info("   Using fallback mathematical validation")
            else:
                logger.info(f"Automated Reasoning status: {status}")
                logger.info("   Using fallback mathematical validation")

        except Exception as e:
            logger.warning(f"Failed to check Automated Reasoning: {e}")
            logger.info("   Using fallback mathematical validation")

    def _get_guardrail_config(self) -> Optional[Dict[str, Any]]:
        """Get guardrail configuration for LLM calls"""
        try:
            if not self.config:
                logger.debug("No config manager available")
                return None

            guardrail_id = self.config.automated_reasoning_guardrail_id
            guardrail_version = self.config.automated_reasoning_guardrail_version
            ar_status = self.config.get("automated_reasoning_status", "unknown")

            logger.debug(f"Guardrail config check:")
            logger.debug(f"   Status: {ar_status}")
            logger.debug(f"   Guardrail ID: {guardrail_id or 'None'}")
            logger.debug(f"   Version: {guardrail_version}")

            if guardrail_id and ar_status == "ready":
                config = {
                    "guardrailIdentifier": guardrail_id,
                    "guardrailVersion": guardrail_version,
                    "trace": "enabled",  # Enable tracing for debugging
                }
                logger.debug(f"Returning guardrail config: {guardrail_id}")
                return config
            elif guardrail_id and ar_status == "creating":
                logger.debug(
                    f"Guardrail exists but status is 'creating', not using yet"
                )
                return None
            else:
                logger.debug(f"No guardrail available (status: {ar_status})")
                return None

        except Exception as e:
            logger.warning(f"Failed to get guardrail config: {e}")
            return None

    def step1_excel_to_markdown(self, excel_path: str) -> str:
        """Step 1: Convert Excel to LLM-readable Markdown with enhanced processing"""
        try:
            from excel_to_markdown import ExcelToMarkdownConverter

            converter = ExcelToMarkdownConverter()
            result = converter.convert_to_markdown(excel_path)

            if result.get("error"):
                raise Exception(f"Excel conversion failed: {result['error']}")

            # Store additional data for later use
            self._excel_data = result

            return result["markdown_content"]

        except Exception as e:
            # Fallback to simple pandas conversion
            logger.warning(f"Enhanced conversion failed, using fallback: {e}")
            try:
                excel_file = pd.ExcelFile(excel_path)
                markdown = f"# Timecard: {Path(excel_path).name}\n\n"

                for sheet in excel_file.sheet_names:
                    df = pd.read_excel(excel_path, sheet_name=sheet)
                    # Clean up unnamed columns
                    df.columns = [
                        col if not str(col).startswith("Unnamed") else ""
                        for col in df.columns
                    ]
                    markdown += f"## {sheet}\n\n"
                    markdown += df.to_markdown(index=False, tablefmt="pipe")
                    markdown += (
                        f"\n\n**Rows:** {len(df)} | **Columns:** {len(df.columns)}\n\n"
                    )

                return markdown
            except Exception as fallback_error:
                raise Exception(f"Excel conversion failed: {fallback_error}")

    def step2_llm_extraction(self, markdown: str) -> Dict[str, Any]:
        """Step 2: LLM extraction with integrated Automated Reasoning validation"""

        # Always use LLM extraction - no pre-processing assumptions
        prompt = f"""
        Analyze this Excel document converted to markdown and extract ALL timecard/payroll data.
        
        This document may contain:
        - Multiple employees and their timecards
        - Various Excel formats (templates, custom layouts, etc.)
        - Employee names, hours worked, pay rates, dates, projects, departments
        - Salary information, overtime calculations
        
        Extract and analyze ALL data, then return ONLY valid JSON in this exact format:
        {{
            "employee_name": "Primary employee name or 'Multiple Employees' if more than one",
            "employee_count": 5,
            "employee_list": ["Employee 1", "Employee 2", "Employee 3"],
            "total_timecards": 15,
            "total_days": 40,
            "total_wage": 8000.0,
            "average_daily_rate": 200.0,
            "pay_period_start": "YYYY-MM-DD",
            "pay_period_end": "YYYY-MM-DD",
            "daily_entries_format": ["employee", "date", "rate", "project", "department"],
            "daily_entries": [
                ["John Doe", "2025-01-15", 200.0, "Project A", "Production"],
                ["Jane Smith", "2025-01-16", 240.0, "Project B", "Audio"],
                ["Mike Johnson", "2025-01-17", 224.0, "Project C", "Video"]
            ],
            "extraction_method": "llm_extraction"
        }}
        
        CRITICAL INSTRUCTIONS: 
        - employee_count = COUNT OF UNIQUE EMPLOYEE NAMES (not rows)
        - total_timecards = TOTAL NUMBER OF TIMECARD ENTRIES/ROWS (can be multiple per employee)
        - Each employee may have multiple timecard entries (different days, projects, etc.)
        - Count total days worked across all entries
        - Calculate total_wage = sum of all daily_rates
        - daily_entries uses COMPACT ARRAY FORMAT: [employee_name, date, daily_rate, project, department]
        - daily_rate is the full day wage (no hourly calculation needed)
        - Include ALL individual timecard entries in daily_entries array (NO LIMITS - MUST MATCH total_timecards)
        - IMPORTANT: If data shows "days" instead of "hours", convert to hours (assume 8 hours per day)
        - IMPORTANT: Parse numeric values carefully - some may be formatted as text
        - IMPORTANT: daily_entries array length MUST equal total_timecards value
        - If no clear data found, use 0 values but still return valid JSON
        
        Example: If John Doe has 3 timecard entries and Jane Smith has 2 entries:
        - employee_count = 2 (unique employees)
        - total_timecards = 5 (total entries)
        - daily_entries = [["John Doe", "2025-01-15", 200.0, "Project A", "Production"], ["John Doe", "2025-01-16", 200.0, "Project A", "Production"], ["John Doe", "2025-01-17", 200.0, "Project B", "Production"], ["Jane Smith", "2025-01-18", 240.0, "Project C", "Audio"], ["Jane Smith", "2025-01-19", 240.0, "Project C", "Audio"]]
        
        PARSING RULES:
        - Extract daily rates directly (no hourly conversion needed)
        - If you see hourly rates, multiply by 8 to get daily rate
        - Parse all numeric values carefully from text format
        - Always ensure daily_entries array has exactly total_timecards number of items
        - Each array item: [employee_name, date, daily_rate, project_name, department_name]
        
        Full Document:
        {markdown}
        
        Return ONLY the JSON object, no explanations.
        """

        try:
            # Define the tool schema for structured output
            tool_schema = {
                "name": "extract_timecard_data",
                "description": "Extract structured timecard data from the provided markdown",
                "inputSchema": {
                    "json": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "properties": {
                            "employee_name": {
                                "type": "string",
                                "description": "Primary employee name",
                            },
                            "employee_count": {
                                "type": "integer",
                                "description": "Total number of employees",
                            },
                            "employee_list": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of all employee names",
                            },
                            "total_timecards": {
                                "type": "integer",
                                "description": "Total number of timecard entries",
                            },
                            "total_days": {
                                "type": "integer",
                                "description": "Total working days",
                            },
                            "total_wage": {
                                "type": "number",
                                "description": "Total wage amount",
                            },
                            "average_daily_rate": {
                                "type": "number",
                                "description": "Average daily rate",
                            },
                            "pay_period_start": {
                                "type": "string",
                                "description": "Pay period start date (YYYY-MM-DD)",
                            },
                            "pay_period_end": {
                                "type": "string",
                                "description": "Pay period end date (YYYY-MM-DD)",
                            },
                            "daily_entries": {
                                "type": "array",
                                "items": {
                                    "type": "array",
                                    "prefixItems": [
                                        {
                                            "type": "string",
                                            "description": "Employee name",
                                        },
                                        {
                                            "type": "string",
                                            "description": "Date (YYYY-MM-DD)",
                                        },
                                        {"type": "number", "description": "Daily rate"},
                                        {
                                            "type": "string",
                                            "description": "Project/Show",
                                        },
                                        {"type": "string", "description": "Department"},
                                    ],
                                },
                                "description": "Array of daily entries [employee, date, rate, project, department]",
                            },
                        },
                        "required": [
                            "employee_name",
                            "employee_count",
                            "total_timecards",
                            "total_days",
                            "total_wage",
                            "average_daily_rate",
                            "daily_entries",
                        ],
                    }
                },
            }

            # Get model ID from configuration
            model_id = (
                self.config.bedrock_model_id
                if self.config
                else "us.anthropic.claude-sonnet-4-20250514-v1:0"
            )
            logger.info(f"Using model ID for extraction: {model_id}")

            # Set max tokens based on model
            max_tokens = self._get_max_tokens_for_model(model_id)

            # Get guardrail configuration for mathematical validation
            guardrail_config = self._get_guardrail_config()

            # Use Converse API with Tool Use and Guardrail - with retry logic
            converse_params = {
                "modelId": model_id,
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "toolConfig": {"tools": [{"toolSpec": tool_schema}]},
                "inferenceConfig": {
                    "maxTokens": max_tokens,
                    "temperature": 0.1,
                    "topP": 1,
                },
            }

            # Add guardrail configuration if available
            if guardrail_config:
                converse_params["guardrailConfig"] = guardrail_config
                guardrail_id = guardrail_config.get("guardrailIdentifier", "unknown")
                logger.info(f"Using Automated Reasoning Guardrail: {guardrail_id}")
                logger.info(
                    f"   Policy ARN: {self.config.automated_reasoning_policy_arn if self.config else 'unknown'}"
                )
            else:
                ar_status = (
                    self.config.get("automated_reasoning_status", "unknown")
                    if self.config
                    else "unknown"
                )
                logger.info(f"Automated Reasoning NOT active (status: {ar_status})")
                logger.info("   Using fallback mathematical validation")

            response = self._call_bedrock_with_retry(**converse_params)

            # Extract tool use result and guardrail information
            output_message = response["output"]["message"]

            # Check for guardrail intervention
            guardrail_action = "NONE"
            guardrail_findings = []
            validation_passed = True
            validation_confidence = 1.0

            if "trace" in response and "guardrail" in response["trace"]:
                guardrail_trace = response["trace"]["guardrail"]
                guardrail_action = guardrail_trace.get("action", "NONE")

                logger.info(f"Automated Reasoning Guardrail Response:")
                logger.info(f"   Action: {guardrail_action}")

                # Extract Automated Reasoning findings if available
                if "modelOutput" in guardrail_trace:
                    model_output = guardrail_trace["modelOutput"]
                    if (
                        "assessments" in model_output
                        and "automatedReasoning" in model_output["assessments"]
                    ):
                        ar_assessment = model_output["assessments"][
                            "automatedReasoning"
                        ]
                        guardrail_findings = ar_assessment.get("findings", [])

                        logger.info(
                            f"   Automated Reasoning Findings: {len(guardrail_findings)} findings"
                        )
                        for i, finding in enumerate(guardrail_findings):
                            result = finding.get("result", "UNKNOWN")
                            rule_desc = finding.get("ruleDescription", "No description")
                            logger.info(f"     Finding {i+1}: {result} - {rule_desc}")

                        # Check if validation passed
                        if guardrail_action in ["GUARDRAIL_INTERVENED", "BLOCKED"]:
                            validation_passed = False
                            validation_confidence = 0.3
                            logger.info(
                                f"   Validation FAILED: Guardrail {guardrail_action}"
                            )
                        elif any(
                            f.get("result") == "INVALID" for f in guardrail_findings
                        ):
                            validation_passed = False
                            validation_confidence = 0.5
                            logger.info(
                                f"   Validation FAILED: Invalid findings detected"
                            )
                        elif any(
                            f.get("result") == "SATISFIABLE" for f in guardrail_findings
                        ):
                            validation_confidence = 0.7
                            logger.info(f"   Validation PARTIAL: Satisfiable findings")
                        else:
                            logger.info(f"   Validation PASSED: All checks successful")
                    else:
                        logger.info(
                            f"   No Automated Reasoning assessments found in trace"
                        )
                else:
                    logger.info(f"   No model output found in guardrail trace")
            else:
                if guardrail_config:
                    logger.warning(
                        f"Guardrail configured but no trace found in response"
                    )
                    logger.warning(
                        f"   This may indicate the guardrail is not properly attached"
                    )
                else:
                    logger.info(
                        f"No guardrail trace (expected - no guardrail configured)"
                    )

            if "content" not in output_message:
                raise Exception("No content in response")

            tool_use_content = None
            for content_item in output_message["content"]:
                if content_item.get("toolUse"):
                    tool_use_content = content_item["toolUse"]["input"]
                    break

            if not tool_use_content:
                # Fallback to text content if no tool use
                text_content = None
                for content_item in output_message["content"]:
                    if content_item.get("text"):
                        text_content = content_item["text"].strip()
                        break

                if text_content:
                    # Try to parse JSON from text
                    if text_content.startswith("```"):
                        text_content = (
                            text_content.replace("```json", "")
                            .replace("```", "")
                            .strip()
                        )
                    extracted = json.loads(text_content)
                else:
                    raise Exception("No tool use or text content found in response")
            else:
                extracted = tool_use_content

            extracted["extraction_method"] = (
                "tool_use_with_guardrail" if guardrail_action != "NONE" else "tool_use"
            )
            extracted["model_info"] = {
                "model_id": model_id,
                "extraction_model": model_id,
                "max_tokens": max_tokens,
                "guardrail_applied": guardrail_action != "NONE",
            }

            # Add validation results from guardrail
            extracted["validation_passed"] = validation_passed
            extracted["validation_method"] = (
                "automated_reasoning" if guardrail_findings else "none"
            )
            extracted["validation_findings"] = guardrail_findings
            extracted["validation_confidence"] = validation_confidence
            extracted["guardrail_action"] = guardrail_action
            extracted["mathematical_consistency"] = self._is_mathematically_consistent(
                extracted
            )

            # Post-process and validate the extracted data
            extracted = self._post_process_extracted_data(extracted)

            return extracted

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            # Enhanced fallback with better defaults
            model_id = (
                self.config.bedrock_model_id
                if self.config
                else "us.anthropic.claude-sonnet-4-20250514-v1:0"
            )
            return {
                "employee_name": "Extraction Failed",
                "employee_count": 0,
                "employee_list": [],
                "total_timecards": 0,
                "total_days": 0,
                "unique_days": 0,
                "total_wage": 0.0,
                "average_daily_rate": 0.0,
                "pay_period_start": "2025-01-01",
                "pay_period_end": "2025-01-31",
                "daily_entries": [],
                "extraction_method": "fallback",
                "model_info": {
                    "model_id": model_id,
                    "extraction_model": model_id,
                    "error": str(e),
                },
                "error": str(e),
            }

    def _post_process_extracted_data(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process extracted data to ensure accuracy"""
        daily_entries = extracted.get("daily_entries", [])

        if not daily_entries:
            return extracted

        # Calculate accurate statistics from daily_entries
        total_timecards = len(daily_entries)

        # Get unique dates and employees
        unique_dates = set()
        unique_employees = set()
        total_wage = 0.0

        for entry in daily_entries:
            if len(entry) >= 5:
                employee_name = entry[0]
                date = entry[1]
                daily_rate = float(entry[2]) if entry[2] else 0.0

                unique_employees.add(employee_name)
                unique_dates.add(date)
                total_wage += daily_rate

        unique_days = len(unique_dates)
        employee_count = len(unique_employees)
        employee_list = list(unique_employees)

        # Calculate date range
        sorted_dates = sorted(list(unique_dates))
        pay_period_start = sorted_dates[0] if sorted_dates else "N/A"
        pay_period_end = sorted_dates[-1] if sorted_dates else "N/A"

        # Calculate average daily rate
        average_daily_rate = (
            total_wage / total_timecards if total_timecards > 0 else 0.0
        )

        # Update extracted data with corrected values
        extracted.update(
            {
                "total_timecards": total_timecards,
                "total_days": total_timecards,  # Keep this for backward compatibility
                "unique_days": unique_days,  # New field for actual unique days
                "employee_count": employee_count,
                "employee_list": employee_list,
                "employee_name": (
                    employee_list[0]
                    if len(employee_list) == 1
                    else f"Multiple Employees ({employee_count})"
                ),
                "total_wage": round(total_wage, 2),
                "average_daily_rate": round(average_daily_rate, 2),
                "pay_period_start": pay_period_start,
                "pay_period_end": pay_period_end,
            }
        )

        logger.info(
            f"Post-processed data: {employee_count} employees, {total_timecards} timecards, "
            f"{unique_days} unique days, ${total_wage:.2f} total wage"
        )

        return extracted

    def step3_automated_reasoning(
        self, extracted_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Step 3: Process validation results from step2 and generate final report"""

        # Extract key data with safe conversion
        employee_name = extracted_data.get("employee_name", "Unknown")
        total_days = int(extracted_data.get("total_days") or 0)
        unique_days = int(extracted_data.get("unique_days", total_days) or 0)
        average_daily_rate = float(extracted_data.get("average_daily_rate") or 0)
        total_wage = float(extracted_data.get("total_wage") or 0)

        # Get validation results from step2
        validation_passed = extracted_data.get("validation_passed", True)
        validation_method = extracted_data.get("validation_method", "none")
        validation_findings = extracted_data.get("validation_findings", [])
        mathematical_consistency = extracted_data.get("mathematical_consistency", True)
        guardrail_action = extracted_data.get("guardrail_action", "NONE")

        # Log validation method used
        if validation_method == "automated_reasoning":
            policy_arn = (
                self.config.automated_reasoning_policy_arn if self.config else "unknown"
            )
            logger.info(f"Step3: Processing Automated Reasoning results")
            logger.info(f"   Policy ARN: {policy_arn}")
            logger.info(f"   Guardrail Action: {guardrail_action}")
            logger.info(f"   Validation Passed: {validation_passed}")
            logger.info(f"   Findings: {len(validation_findings)} findings")
        else:
            logger.info(f"Step3: Using fallback mathematical validation")
            logger.info(f"   Method: {validation_method}")
            logger.info(f"   Mathematical Consistency: {mathematical_consistency}")

        # Calculate pay (for daily rate system, pay equals total wage)
        pay_calculation = {
            "regular_pay": total_wage,
            "overtime_pay": 0.0,  # No overtime concept in daily rate
            "total_pay": total_wage,
            "pay_type": "daily_rate",
        }

        # Determine validation issues based on step2 results
        validation_issues = []
        requires_human_review = False

        if not validation_passed:
            if validation_method == "automated_reasoning":
                for finding in validation_findings:
                    if finding.get("result") == "INVALID":
                        rule_desc = finding.get(
                            "ruleDescription", "Mathematical validation failed"
                        )
                        validation_issues.append(f"Data integrity issue: {rule_desc}")
            elif not mathematical_consistency:
                validation_issues.append(
                    "Mathematical inconsistencies detected in timecard data"
                )

        # If no Automated Reasoning, fall back to basic mathematical check
        if validation_method == "none" and not mathematical_consistency:
            math_errors = self._get_mathematical_errors(extracted_data)
            validation_issues.extend(math_errors)

        # Determine final result based on Automated Reasoning
        guardrail_action = extracted_data.get("guardrail_action", "NONE")
        if guardrail_action in ["GUARDRAIL_INTERVENED", "BLOCKED"]:
            final_result = ValidationResult.INVALID
        elif validation_issues:
            final_result = ValidationResult.INVALID
        elif validation_passed:
            final_result = ValidationResult.VALID
        else:
            final_result = ValidationResult.SATISFIABLE

        # Get model info from extracted data or use default
        model_info = extracted_data.get(
            "model_info",
            {
                "model_id": (
                    self.config.bedrock_model_id
                    if self.config
                    else "us.anthropic.claude-sonnet-4-20250514-v1:0"
                ),
                "validation_model": validation_method,
            },
        )

        return {
            "validation_result": final_result.value,
            "employee_name": employee_name,
            "total_days": total_days,
            "unique_days": unique_days,
            "average_daily_rate": average_daily_rate,
            "total_wage": total_wage,
            "pay_calculation": pay_calculation,
            "validation_issues": validation_issues,
            "requires_human_review": len(validation_issues) > 0,
            "reasoning_confidence": extracted_data.get("validation_confidence", 0.0),
            "reasoning_findings": validation_findings,
            "automated_reasoning_result": guardrail_action,
            "validation_method": validation_method,
            "mathematical_consistency": mathematical_consistency,
            "model_info": model_info,
            "mathematical_validation": {
                "sum_correct": self._check_sum_calculation(extracted_data),
                "average_correct": self._check_average_calculation(extracted_data),
                "count_correct": self._check_count_consistency(extracted_data),
                "data_integrity": self._check_data_integrity(extracted_data),
            },
        }

    def _calculate_daily_rate_pay(
        self,
        total_days: int,
        average_daily_rate: float,
        total_wage: float,
        is_salary_exempt: bool,
    ) -> Dict[str, Any]:
        """Calculate total pay for daily rate system"""
        if is_salary_exempt:
            return {
                "regular_pay": total_wage,
                "overtime_pay": 0.0,
                "total_pay": total_wage,
                "pay_type": "salary_exempt",
            }

        return {
            "regular_pay": round(total_wage, 2),
            "overtime_pay": 0.0,  # No overtime concept in daily rate
            "total_pay": round(total_wage, 2),
            "pay_type": "daily_rate",
        }

    def _is_mathematically_consistent(self, extracted_data: Dict[str, Any]) -> bool:
        """Check mathematical consistency of extracted timecard data"""

        try:
            daily_entries = extracted_data.get("daily_entries", [])
            total_wage = float(extracted_data.get("total_wage", 0))
            average_daily_rate = float(extracted_data.get("average_daily_rate", 0))
            employee_count = int(extracted_data.get("employee_count", 0))
            total_days = int(extracted_data.get("total_days", 0))

            # Check if daily entries exist
            if not daily_entries:
                return total_wage == 0 and average_daily_rate == 0 and total_days == 0

            # Calculate actual values from daily entries
            actual_sum = sum(
                float(entry[2]) if len(entry) > 2 else 0 for entry in daily_entries
            )
            actual_avg = actual_sum / len(daily_entries) if daily_entries else 0
            actual_unique_employees = len(
                set(entry[0] for entry in daily_entries if len(entry) > 0)
            )

            # Check mathematical consistency (with small tolerance for floating point)
            tolerance = 0.01

            # Sum validation
            if abs(actual_sum - total_wage) > tolerance:
                return False

            # Average validation
            if abs(actual_avg - average_daily_rate) > tolerance:
                return False

            # Count validation
            if actual_unique_employees != employee_count:
                return False

            # Length validation
            if len(daily_entries) != total_days:
                return False

            # Check for negative values
            if any(float(entry[2]) < 0 for entry in daily_entries if len(entry) > 2):
                return False

            # Check for empty critical fields
            for entry in daily_entries:
                if (
                    len(entry) < 5
                ):  # Should have [employee, date, rate, project, department]
                    return False
                if (
                    not entry[0] or not entry[1] or not entry[3] or not entry[4]
                ):  # Check non-empty strings
                    return False

            return True

        except (ValueError, TypeError, IndexError) as e:
            logger.error(f"Error checking mathematical consistency: {e}")
            return False

    def _check_sum_calculation(self, extracted_data: Dict[str, Any]) -> bool:
        """Check if total wage equals sum of daily rates"""
        try:
            daily_entries = extracted_data.get("daily_entries", [])
            total_wage = float(extracted_data.get("total_wage", 0))

            if not daily_entries:
                return total_wage == 0

            actual_sum = sum(
                float(entry[2]) if len(entry) > 2 else 0 for entry in daily_entries
            )
            return abs(actual_sum - total_wage) < 0.01

        except (ValueError, TypeError, IndexError):
            return False

    def _check_average_calculation(self, extracted_data: Dict[str, Any]) -> bool:
        """Check if average daily rate is correctly calculated"""
        try:
            daily_entries = extracted_data.get("daily_entries", [])
            average_daily_rate = float(extracted_data.get("average_daily_rate", 0))
            total_wage = float(extracted_data.get("total_wage", 0))

            if not daily_entries:
                return average_daily_rate == 0

            expected_avg = total_wage / len(daily_entries)
            return abs(expected_avg - average_daily_rate) < 0.01

        except (ValueError, TypeError, ZeroDivisionError):
            return False

    def _check_count_consistency(self, extracted_data: Dict[str, Any]) -> bool:
        """Check if employee count and timecard count are consistent"""
        try:
            daily_entries = extracted_data.get("daily_entries", [])
            employee_count = int(extracted_data.get("employee_count", 0))
            total_days = int(extracted_data.get("total_days", 0))

            if not daily_entries:
                return employee_count == 0 and total_days == 0

            # Check employee count
            actual_unique_employees = len(
                set(entry[0] for entry in daily_entries if len(entry) > 0)
            )
            if actual_unique_employees != employee_count:
                return False

            # Check total timecard count
            if len(daily_entries) != total_days:
                return False

            return True

        except (ValueError, TypeError, IndexError):
            return False

    def _check_data_integrity(self, extracted_data: Dict[str, Any]) -> bool:
        """Check data integrity (no negative values, missing fields, etc.)"""
        try:
            daily_entries = extracted_data.get("daily_entries", [])

            for entry in daily_entries:
                # Check array structure
                if (
                    len(entry) < 5
                ):  # Should have [employee, date, rate, project, department]
                    return False

                # Check for empty critical fields
                if not entry[0] or not entry[1] or not entry[3] or not entry[4]:
                    return False

                # Check for negative rates
                if float(entry[2]) < 0:
                    return False

            return True

        except (ValueError, TypeError, IndexError):
            return False

    def _get_mathematical_errors(self, extracted_data: Dict[str, Any]) -> List[str]:
        """Get specific mathematical errors in the data"""
        errors = []

        if not self._check_sum_calculation(extracted_data):
            daily_entries = extracted_data.get("daily_entries", [])
            total_wage = float(extracted_data.get("total_wage", 0))
            actual_sum = sum(
                float(entry[2]) if len(entry) > 2 else 0 for entry in daily_entries
            )
            errors.append(
                f"Sum calculation error: Total wage ({total_wage:.2f}) ≠ Sum of daily rates ({actual_sum:.2f})"
            )

        if not self._check_average_calculation(extracted_data):
            average_daily_rate = float(extracted_data.get("average_daily_rate", 0))
            total_wage = float(extracted_data.get("total_wage", 0))
            daily_entries = extracted_data.get("daily_entries", [])
            expected_avg = total_wage / len(daily_entries) if daily_entries else 0
            errors.append(
                f"Average calculation error: Reported ({average_daily_rate:.2f}) ≠ Calculated ({expected_avg:.2f})"
            )

        if not self._check_count_consistency(extracted_data):
            daily_entries = extracted_data.get("daily_entries", [])
            employee_count = int(extracted_data.get("employee_count", 0))
            total_days = int(extracted_data.get("total_days", 0))
            actual_unique = len(
                set(entry[0] for entry in daily_entries if len(entry) > 0)
            )

            if actual_unique != employee_count:
                errors.append(
                    f"Employee count mismatch: Reported ({employee_count}) ≠ Actual unique employees ({actual_unique})"
                )

            if len(daily_entries) != total_days:
                errors.append(
                    f"Timecard count mismatch: Reported ({total_days}) ≠ Daily entries length ({len(daily_entries)})"
                )

        if not self._check_data_integrity(extracted_data):
            errors.append(
                "Data integrity issues: negative values, missing fields, or invalid structure"
            )

        return errors

    def _fallback_validation(
        self,
        average_daily_rate: float,
        total_days: int,
        weekly_equivalent: float,
        is_salary_exempt: bool,
    ) -> Dict[str, Any]:
        """Fallback validation when Automated Reasoning is not available - focuses on mathematical consistency"""

        validation_issues = []

        # Get the extracted data for mathematical validation
        # This is a simplified fallback that checks basic mathematical consistency

        # Check for obviously invalid values
        if average_daily_rate < 0:
            validation_issues.append("Negative daily rate detected")

        if total_days < 0:
            validation_issues.append("Negative total days detected")

        if total_days == 0 and average_daily_rate > 0:
            validation_issues.append("Zero days worked but positive daily rate")

        if total_days > 0 and average_daily_rate == 0:
            validation_issues.append("Days worked but zero daily rate")

        return {
            "action": "BLOCK" if validation_issues else "NONE",
            "findings": [
                {
                    "result": "INVALID" if validation_issues else "VALID",
                    "rule_id": "fallback_mathematical_validation",
                    "rule_description": "Basic mathematical consistency check",
                    "variables": {
                        "average_daily_rate": average_daily_rate,
                        "total_days": total_days,
                        "weekly_equivalent": weekly_equivalent,
                    },
                    "suggestions": validation_issues,
                }
            ],
            "confidence": (
                0.6 if not validation_issues else 0.2
            ),  # Lower confidence for fallback
            "outputs": [],
            "raw_response": {"fallback": True, "type": "mathematical_validation"},
        }

    def get_review_queue(self) -> List[Dict[str, Any]]:
        """Get pending reviews sorted by priority"""
        pending = [item for item in self.review_queue if item["status"] == "pending"]
        return sorted(
            pending,
            key=lambda x: {"high": 3, "medium": 2, "low": 1}[x["priority"]],
            reverse=True,
        )

    def process(self, excel_path: str, progress_callback=None) -> Dict[str, Any]:
        """Complete 3-step pipeline execution"""
        try:
            # Step 1: Excel → Markdown
            logger.info("Step 1: Converting Excel to Markdown...")
            if progress_callback:
                progress_callback(20)
            markdown = self.step1_excel_to_markdown(excel_path)

            # Step 2: Markdown → LLM Extraction
            logger.info("Step 2: LLM data extraction...")
            if progress_callback:
                progress_callback(40)
            extracted_data = self.step2_llm_extraction(markdown)

            # Step 3: Automated Reasoning Validation
            logger.info("Step 3: Rule-based validation...")
            if progress_callback:
                progress_callback(80)
            validation = self.step3_automated_reasoning(extracted_data)

            return {
                "status": "success",
                "file_path": excel_path,
                "extracted_data": extracted_data,
                "validation": validation,
                "markdown_preview": markdown,
                "pipeline_steps": [
                    "excel_to_markdown",
                    "llm_extraction",
                    "automated_reasoning",
                ],
            }

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            return {"status": "error", "error": str(e), "file_path": excel_path}

    def _call_bedrock_with_retry(self, **kwargs):
        """Call Bedrock API with exponential backoff retry logic"""
        import time
        import random
        from botocore.exceptions import ClientError

        max_retries = 5
        base_delay = 1

        for attempt in range(max_retries):
            try:
                return self.bedrock.converse(**kwargs)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                if error_code in ["ThrottlingException", "TooManyRequestsException"]:
                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter
                        delay = base_delay * (2**attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"Rate limited, retrying in {delay:.2f} seconds (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Max retries exceeded for rate limiting")
                        raise
                else:
                    # For other errors, don't retry
                    raise

        raise Exception("Unexpected error in retry logic")

    def _get_max_tokens_for_model(self, model_id: str) -> int:
        """Get maximum tokens allowed for the specified model"""
        # Model-specific token limits
        model_limits = {
            # Claude Opus 4.1 has a 32K token limit
            "us.anthropic.claude-opus-4-1-20250805-v1:0": 32000,
            # Claude Sonnet 4 has higher limits
            "us.anthropic.claude-sonnet-4-20250514-v1:0": 32000,
            # Claude 3.7 Sonnet has higher limits
            "us.anthropic.claude-3-7-sonnet-20250219-v1:0": 32000,
            # Legacy models (fallback)
            "anthropic.claude-3-sonnet-20240229-v1:0": 16000,
        }

        # Return model-specific limit or default to 32000 for safety
        return model_limits.get(model_id, 32000)


# Simple usage example
if __name__ == "__main__":
    pipeline = TimecardPipeline()
    result = pipeline.process("sample_timecard.xlsx")
    print(json.dumps(result, indent=2))
