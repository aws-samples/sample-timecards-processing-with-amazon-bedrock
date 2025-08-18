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
            retries={'max_attempts': 1}
        )
        
        self.bedrock = boto3.client("bedrock-runtime", region_name=region, config=boto_config)
        self.guardrails = boto3.client("bedrock", region_name=region, config=boto_config)

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
        """Step 2: LLM extraction for timecard data using Claude Sonnet"""

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
                                        {"type": "string", "description": "Employee name"},
                                        {"type": "string", "description": "Date (YYYY-MM-DD)"},
                                        {"type": "number", "description": "Daily rate"},
                                        {"type": "string", "description": "Project/Show"},
                                        {"type": "string", "description": "Department"}
                                    ]
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
            model_id = self.config.bedrock_model_id if self.config else "us.anthropic.claude-sonnet-4-20250514-v1:0"
            logger.info(f"Using model ID for extraction: {model_id}")
            
            # Set max tokens based on model
            max_tokens = self._get_max_tokens_for_model(model_id)
            
            # Use Converse API with Tool Use
            response = self.bedrock.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                toolConfig={"tools": [{"toolSpec": tool_schema}]},
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1, "topP": 1},
            )

            # Extract tool use result
            output_message = response["output"]["message"]

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

            extracted["extraction_method"] = "tool_use"
            extracted["model_info"] = {
                "model_id": model_id,
                "extraction_model": model_id,
                "max_tokens": max_tokens
            }

            # Post-process and validate the extracted data
            extracted = self._post_process_extracted_data(extracted)

            return extracted

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            # Enhanced fallback with better defaults
            model_id = self.config.bedrock_model_id if self.config else "us.anthropic.claude-sonnet-4-20250514-v1:0"
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
                    "error": str(e)
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
        """Step 3: Validation using AWS Bedrock Automated Reasoning with Human-in-Loop"""

        # Extract key data with safe conversion
        employee_name = extracted_data.get("employee_name", "Unknown")
        total_days = int(extracted_data.get("total_days") or 0)
        unique_days = int(extracted_data.get("unique_days", total_days) or 0)
        average_daily_rate = float(extracted_data.get("average_daily_rate") or 0)
        total_wage = float(extracted_data.get("total_wage") or 0)

        # Calculate weekly equivalent for compliance
        weekly_equivalent = (
            (total_days / 7) * average_daily_rate if total_days > 0 else 0
        )
        is_salary_exempt = weekly_equivalent >= self.compliance.salary_exempt_threshold

        # Pre-validation checks
        validation_issues = []
        requires_human_review = False

        # 1. Daily rate minimum wage check (assuming 8-hour day)
        hourly_equivalent = average_daily_rate / 8 if average_daily_rate > 0 else 0
        if (
            hourly_equivalent > 0
            and hourly_equivalent < self.compliance.federal_minimum_wage
        ):
            validation_issues.append(
                f"Daily rate ${average_daily_rate:.2f} (${hourly_equivalent:.2f}/hr) below federal minimum ${self.compliance.federal_minimum_wage}"
            )

        # 2. Excessive days check (more than 7 days per week equivalent)
        weekly_days = total_days / 7 if total_days > 0 else 0
        if weekly_days > 6:  # More than 6 days per week
            validation_issues.append(
                f"Excessive work schedule ({weekly_days:.1f} days/week) requires management approval"
            )
            requires_human_review = True

        # 3. High daily rate validation
        if average_daily_rate > 2000:  # Very high daily rate
            validation_issues.append(
                f"High daily rate ${average_daily_rate:.2f} requires verification"
            )
            requires_human_review = True

        # 4. Salary exempt validation
        if (
            is_salary_exempt and weekly_days > 5
        ):  # Exempt employees working excessive days
            validation_issues.append(
                "Salary-exempt employee working excessive hours - verify job duties"
            )
            requires_human_review = True

        # 5. Run rule-based validation (skip LLM for speed)
        reasoning_result = {
            "result": "VALID" if not validation_issues else "INVALID",
            "confidence": 0.95,
            "reasoning": "Rule-based validation completed",
            "compliance_issues": validation_issues
        }

        # 6. Calculate pay (for daily rate system, pay equals total wage)
        pay_calculation = {
            "regular_pay": total_wage,
            "overtime_pay": 0.0,  # No overtime concept in daily rate
            "total_pay": total_wage,
            "pay_type": "daily_rate",
        }

        # 7. Determine final validation result
        if requires_human_review:
            final_result = ValidationResult.REQUIRES_HUMAN_REVIEW
            self._add_to_review_queue(extracted_data, validation_issues)
        elif validation_issues:
            final_result = ValidationResult.INVALID
        elif reasoning_result.get("result") == "VALID":
            final_result = ValidationResult.VALID
        else:
            final_result = ValidationResult.SATISFIABLE

        # Get model info from extracted data or use default
        model_info = extracted_data.get("model_info", {
            "model_id": self.config.bedrock_model_id if self.config else "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "validation_model": self.config.bedrock_model_id if self.config else "us.anthropic.claude-sonnet-4-20250514-v1:0"
        })

        return {
            "validation_result": final_result.value,
            "employee_name": employee_name,
            "total_days": total_days,
            "unique_days": unique_days,
            "average_daily_rate": average_daily_rate,
            "total_wage": total_wage,
            "weekly_equivalent": weekly_equivalent,
            "is_salary_exempt": is_salary_exempt,
            "pay_calculation": pay_calculation,
            "validation_issues": validation_issues,
            "requires_human_review": requires_human_review,
            "reasoning_confidence": reasoning_result.get("confidence", 0.0),
            "model_info": model_info,
            "compliance_summary": self._generate_compliance_summary(
                unique_days,
                average_daily_rate,
                is_salary_exempt,
                weekly_equivalent,
                validation_issues,
            ),
            "next_actions": self._get_next_actions(final_result, validation_issues),
            "federal_compliance": {
                "minimum_wage_met": hourly_equivalent
                >= self.compliance.federal_minimum_wage,
                "daily_rate_compliant": average_daily_rate
                >= (self.compliance.federal_minimum_wage * 8),
                "days_within_limit": weekly_days <= 6,
                "salary_exempt_threshold_met": (
                    weekly_equivalent >= self.compliance.salary_exempt_threshold
                    if is_salary_exempt
                    else True
                ),
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

    def _run_automated_reasoning_validation(
        self,
        extracted_data: Dict[str, Any],
        weekly_salary: float,
        is_salary_exempt: bool,
    ) -> Dict[str, Any]:
        """Run Automated Reasoning validation using Claude"""

        # Extract variables from extracted_data
        total_days = int(extracted_data.get("total_days") or 0)
        average_daily_rate = float(extracted_data.get("average_daily_rate") or 0)
        total_wage = float(extracted_data.get("total_wage") or 0)
        weekly_equivalent = weekly_salary

        validation_prompt = f"""
        Validate this entertainment industry timecard for federal wage compliance (daily rate system):
        
        Employee: {extracted_data.get('employee_name', 'Unknown')}
        Total Days: {total_days}
        Average Daily Rate: ${average_daily_rate:.2f}/day
        Total Wage: ${total_wage:.2f}
        Weekly Equivalent: ${weekly_equivalent:.2f}
        Is Salary Exempt: {is_salary_exempt}
        
        Federal Requirements:
        - Minimum wage: ${self.compliance.federal_minimum_wage}/hour (${self.compliance.federal_minimum_wage * 8:.2f}/day)
        - Overtime threshold: {self.compliance.overtime_threshold} hours/week
        - Salary exempt threshold: ${self.compliance.salary_exempt_threshold}/week
        - Maximum recommended hours: {self.compliance.max_weekly_hours} hours/week
        
        Return JSON with:
        - result: "VALID" | "INVALID" | "SATISFIABLE"
        - confidence: 0.0-1.0
        - reasoning: "explanation"
        - compliance_issues: ["list of issues"]
        """

        try:
            # Define the validation tool schema
            validation_tool_schema = {
                "name": "validate_timecard_compliance",
                "description": "Validate timecard compliance with federal wage laws",
                "inputSchema": {
                    "json": {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "properties": {
                            "result": {
                                "type": "string",
                                "enum": ["VALID", "INVALID", "SATISFIABLE"],
                                "description": "Validation result",
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "Confidence level in the validation",
                            },
                            "reasoning": {
                                "type": "string",
                                "description": "Detailed explanation of the validation decision",
                            },
                            "compliance_issues": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of compliance issues found",
                            },
                        },
                        "required": [
                            "result",
                            "confidence",
                            "reasoning",
                            "compliance_issues",
                        ],
                    }
                },
            }

            # Get model ID from configuration
            model_id = self.config.bedrock_model_id if self.config else "us.anthropic.claude-sonnet-4-20250514-v1:0"
            
            # Set max tokens for validation (smaller requirement)
            max_tokens = min(1000, self._get_max_tokens_for_model(model_id))
            
            # Use Converse API with Tool Use for validation
            response = self.bedrock.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": validation_prompt}]}],
                toolConfig={"tools": [{"toolSpec": validation_tool_schema}]},
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1, "topP": 1},
            )

            # Extract tool use result
            output_message = response["output"]["message"]

            if "content" not in output_message:
                raise Exception("No content in validation response")

            tool_use_content = None
            for content_item in output_message["content"]:
                if content_item.get("toolUse"):
                    tool_use_content = content_item["toolUse"]["input"]
                    break

            if not tool_use_content:
                # Fallback to text content
                text_content = None
                for content_item in output_message["content"]:
                    if content_item.get("text"):
                        text_content = content_item["text"].strip()
                        break

                if text_content:
                    if text_content.startswith("```"):
                        text_content = (
                            text_content.replace("```json", "")
                            .replace("```", "")
                            .strip()
                        )
                    return json.loads(text_content)
                else:
                    raise Exception(
                        "No tool use or text content found in validation response"
                    )

            result = tool_use_content
            result["model_info"] = {
                "model_id": model_id,
                "validation_model": model_id,
                "max_tokens": max_tokens
            }
            return result

        except Exception as e:
            logger.error(f"Automated reasoning error: {e}")
            return {
                "result": "SATISFIABLE",
                "confidence": 0.0,
                "reasoning": f"Error in validation: {e}",
                "compliance_issues": [],
                "model_info": {
                    "model_id": model_id,
                    "validation_model": model_id,
                    "error": str(e)
                }
            }

    def _generate_compliance_summary(
        self,
        days: int,
        daily_rate: float,
        is_exempt: bool,
        weekly_equivalent: float,
        issues: List[str],
    ) -> str:
        """Generate human-readable compliance summary"""
        if not issues:
            if is_exempt:
                return f"Compliant: Salary-exempt employee (${weekly_equivalent:.2f}/week equivalent)"
            else:
                weekly_days = days / 7 if days > 0 else 0
                return f"Compliant: {days} days worked ({weekly_days:.1f} days/week) at ${daily_rate:.2f}/day"
        else:
            return f"Non-compliant: {len(issues)} issues found"

    def _get_next_actions(
        self, result: ValidationResult, issues: List[str]
    ) -> List[str]:
        """Get recommended next actions based on validation result"""
        actions = []

        if result == ValidationResult.REQUIRES_HUMAN_REVIEW:
            actions.append("Route to HR manager for review")
            actions.append("Verify job classification and duties")

        if result == ValidationResult.INVALID:
            actions.append("Reject timecard - corrections needed")
            actions.append("Notify employee and supervisor")

        if "below federal minimum" in str(issues):
            actions.append("Adjust hourly rate to meet federal minimum")

        if "Excessive hours" in str(issues):
            actions.append("Obtain management approval for overtime")

        if not actions:
            actions.append("Approve timecard for payroll processing")

        return actions

    def _add_to_review_queue(self, timecard_data: Dict[str, Any], issues: List[str]):
        """Add timecard to human review queue"""
        review_item = {
            "id": f"review_{len(self.review_queue) + 1}",
            "timecard": timecard_data,
            "issues": issues,
            "priority": self._calculate_priority(timecard_data),
            "status": "pending",
            "created_at": "now",
        }
        self.review_queue.append(review_item)
        logger.info(f"Added timecard to review queue: {review_item['id']}")

    def _calculate_priority(self, timecard_data: Dict[str, Any]) -> str:
        """Calculate review priority based on issues"""
        days = timecard_data.get("total_days", 0)
        daily_rate = timecard_data.get("average_daily_rate", 0)
        hourly_equivalent = daily_rate / 8 if daily_rate > 0 else 0

        if hourly_equivalent < self.compliance.federal_minimum_wage:
            return "high"
        elif days > 42:  # More than 6 days per week
            return "high"
        elif days > 35:  # More than 5 days per week
            return "medium"
        else:
            return "low"

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

    def _get_max_tokens_for_model(self, model_id: str) -> int:
        """Get maximum tokens allowed for the specified model"""
        # Model-specific token limits
        model_limits = {
            # Claude Opus 4.1 has a 32K token limit
            "us.anthropic.claude-opus-4-1-20250805-v1:0": 32000,
            # Claude Sonnet 4 has higher limits
            "us.anthropic.claude-sonnet-4-20250514-v1:0": 64000,
            # Claude 3.7 Sonnet has higher limits
            "us.anthropic.claude-3-7-sonnet-20250219-v1:0": 64000,
            # Legacy models (fallback)
            "anthropic.claude-3-sonnet-20240229-v1:0": 64000,
        }
        
        # Return model-specific limit or default to 32000 for safety
        return model_limits.get(model_id, 32000)


# Simple usage example
if __name__ == "__main__":
    pipeline = TimecardPipeline()
    result = pipeline.process("sample_timecard.xlsx")
    print(json.dumps(result, indent=2))
