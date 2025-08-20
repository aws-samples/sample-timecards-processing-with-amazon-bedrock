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
        """Ensure Automated Reasoning is provisioned and properly configured"""
        try:
            from automated_reasoning_provisioner import AutomatedReasoningProvisioner

            logger.info("Verifying Automated Reasoning configuration...")

            # Create provisioner and do thorough check
            provisioner = AutomatedReasoningProvisioner(
                region_name=self.config.aws_region if self.config else "us-west-2",
                config_manager=self.config
            )
            
            result = provisioner.ensure_provisioned()

            status = result.get("status", "unknown")
            policy_arn = result.get("policy_arn")
            guardrail_id = result.get("guardrail_id")
            verified = result.get("verified", False)

            if status == "ready" and verified:
                logger.info("Automated Reasoning is READY and VERIFIED")
                logger.info(f"   Policy ARN: {policy_arn}")
                logger.info(f"   Guardrail ID: {guardrail_id}")
                logger.info("   Mathematical validation will use formal logic")
            elif status == "ready" and not verified:
                logger.warning("Automated Reasoning marked ready but not verified")
                logger.info(f"   Policy ARN: {policy_arn}")
                logger.info(f"   Guardrail ID: {guardrail_id}")
                logger.info("   Using fallback validation until verification complete")
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

            # More lenient check - use guardrail if it exists, regardless of status
            if guardrail_id:
                # Verify guardrail actually exists in AWS
                try:
                    response = self.guardrails.get_guardrail(
                        guardrailIdentifier=guardrail_id
                    )
                    guardrail_status = response.get("status")
                    
                    if guardrail_status == "READY":
                        config = {
                            "guardrailIdentifier": guardrail_id,
                            "guardrailVersion": guardrail_version or "DRAFT",
                            "trace": "enabled",  # Enable tracing for debugging
                        }
                        logger.info(f"Using active guardrail: {guardrail_id} (status: {guardrail_status})")
                        return config
                    else:
                        logger.warning(f"Guardrail exists but not ready: {guardrail_status}")
                        return None
                        
                except Exception as verify_e:
                    logger.warning(f"Guardrail verification failed: {verify_e}")
                    return None
            else:
                logger.debug(f"No guardrail ID configured (status: {ar_status})")
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

            # Debug: Log the full response structure for troubleshooting
            logger.debug(f"Full Bedrock response keys: {list(response.keys())}")
            if "trace" in response:
                trace_data = response["trace"]
                if isinstance(trace_data, dict):
                    logger.debug(f"Trace keys: {list(trace_data.keys())}")
                else:
                    logger.debug(f"Trace is not a dict, type: {type(trace_data)}")

            # Check if guardrail was applied and outputAssessments are available
            output_assessments_found = False
            
            if "trace" in response:
                trace_data = response["trace"]
                
                # Handle both dict and list trace formats
                if isinstance(trace_data, dict) and "guardrail" in trace_data:
                    guardrail_trace = trace_data["guardrail"]
                    guardrail_action = guardrail_trace.get("action", "NONE")
                    
                    logger.info(f"Automated Reasoning Guardrail Response:")
                    logger.info(f"   Action: {guardrail_action}")
                    
                    # Check for outputAssessments
                    if "outputAssessments" in guardrail_trace:
                        output_assessments = guardrail_trace["outputAssessments"]
                        if output_assessments and isinstance(output_assessments, dict):
                            for guardrail_id, assessments in output_assessments.items():
                                if isinstance(assessments, list) and assessments:
                                    for assessment in assessments:
                                        if "automatedReasoningPolicy" in assessment:
                                            ar_data = assessment["automatedReasoningPolicy"]
                                            findings = ar_data.get("findings", [])
                                            if findings:
                                                output_assessments_found = True
                                                guardrail_findings.extend(findings)
                                                logger.info(f"   Found {len(findings)} AR findings in outputAssessments")
                                                
                                                # Process findings for validation
                                                validation_passed, validation_confidence = self._process_ar_findings(findings)
                    
                    if not output_assessments_found:
                        logger.warning("   No outputAssessments found in guardrail trace")
                        logger.info("   Will use explicit apply_guardrail for validation")
                        
                elif isinstance(trace_data, list):
                    logger.debug(f"Trace is a list with {len(trace_data)} items")
                    # Handle list format if needed in the future
                else:
                    logger.debug(f"Trace format not recognized: {type(trace_data)}")
            
            # If no outputAssessments or guardrail not configured, use explicit apply_guardrail
            if guardrail_config and not output_assessments_found:
                logger.info(" Applying explicit guardrail validation...")
                
                # Get the LLM response text for validation
                llm_response_text = ""
                if "content" in output_message:
                    for content_item in output_message["content"]:
                        if content_item.get("toolUse"):
                            # Convert tool use to JSON string for validation
                            llm_response_text = json.dumps(content_item["toolUse"]["input"], indent=2)
                            break
                        elif content_item.get("text"):
                            llm_response_text = content_item["text"]
                            break
                
                if llm_response_text:
                    try:
                        # Truncate content if too long (apply_guardrail has limits)
                        max_content_length = 10000  # Conservative limit
                        if len(llm_response_text) > max_content_length:
                            logger.warning(f"   Content too long ({len(llm_response_text)} chars), truncating to {max_content_length}")
                            llm_response_text = llm_response_text[:max_content_length] + "..."
                        
                        # Apply guardrail explicitly to the LLM response
                        apply_guardrail_response = self.bedrock.apply_guardrail(
                            guardrailIdentifier=guardrail_config["guardrailIdentifier"],
                            guardrailVersion=guardrail_config.get("guardrailVersion", "DRAFT"),
                            source="OUTPUT",
                            content=[{"text": {"text": llm_response_text}}]
                        )
                        
                        # Extract findings from apply_guardrail response
                        explicit_action = apply_guardrail_response.get("action", "NONE")
                        explicit_usage = apply_guardrail_response.get("usage", {})
                        explicit_outputs = apply_guardrail_response.get("outputs", [])
                        
                        logger.info(f"   Explicit Guardrail Action: {explicit_action}")
                        logger.info(f"   Explicit Usage: {explicit_usage}")
                        
                        # Extract AR findings from explicit call
                        explicit_ar_findings = []
                        for output in explicit_outputs:
                            if "automatedReasoning" in output:
                                ar_data = output["automatedReasoning"]
                                findings = ar_data.get("findings", [])
                                explicit_ar_findings.extend(findings)
                        
                        if explicit_ar_findings:
                            logger.info(f"   Found {len(explicit_ar_findings)} AR findings from explicit call")
                            guardrail_findings.extend(explicit_ar_findings)
                            
                            # Process findings for validation
                            validation_passed, validation_confidence = self._process_ar_findings(explicit_ar_findings)
                            
                            # Update guardrail action if explicit call found issues
                            if explicit_action != "NONE":
                                guardrail_action = explicit_action
                        else:
                            logger.info("   No AR findings from explicit guardrail call")
                            
                    except Exception as explicit_error:
                        error_msg = str(explicit_error)
                        logger.error(f"   Explicit guardrail call failed: {error_msg}")
                        
                        # If it's a ValidationException, try with simpler content
                        if "ValidationException" in error_msg and len(llm_response_text) > 1000:
                            logger.info("   Retrying with simplified content...")
                            try:
                                # Extract just the key mathematical data for validation
                                simple_content = f"total_wage: {extracted.get('total_wage', 0)}, daily_entries_count: {len(extracted.get('daily_entries', []))}"
                                
                                apply_guardrail_response = self.bedrock.apply_guardrail(
                                    guardrailIdentifier=guardrail_config["guardrailIdentifier"],
                                    guardrailVersion=guardrail_config.get("guardrailVersion", "DRAFT"),
                                    source="OUTPUT",
                                    content=[{"text": {"text": simple_content}}]
                                )
                                
                                explicit_action = apply_guardrail_response.get("action", "NONE")
                                explicit_usage = apply_guardrail_response.get("usage", {})
                                explicit_outputs = apply_guardrail_response.get("outputs", [])
                                
                                logger.info(f"   Retry Guardrail Action: {explicit_action}")
                                logger.info(f"   Retry Usage: {explicit_usage}")
                                
                                # Process any findings from retry
                                explicit_ar_findings = []
                                for output in explicit_outputs:
                                    if "automatedReasoning" in output:
                                        ar_data = output["automatedReasoning"]
                                        findings = ar_data.get("findings", [])
                                        explicit_ar_findings.extend(findings)
                                
                                if explicit_ar_findings:
                                    logger.info(f"   Found {len(explicit_ar_findings)} AR findings from retry")
                                    guardrail_findings.extend(explicit_ar_findings)
                                    validation_passed, validation_confidence = self._process_ar_findings(explicit_ar_findings)
                                    if explicit_action != "NONE":
                                        guardrail_action = explicit_action
                                        
                            except Exception as retry_error:
                                logger.error(f"   Retry also failed: {retry_error}")
                else:
                    logger.warning("   No LLM response text found for explicit validation")
            
            # Log final validation result
            if not validation_passed:
                logger.info(f"   Final Validation: FAILED (confidence: {validation_confidence})")
            else:
                logger.info(f"   Final Validation: PASSED")
                
            if not guardrail_config:
                logger.info("No guardrail trace (expected - no guardrail configured)")

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

    def test_guardrail_with_invalid_data(self) -> Dict[str, Any]:
        """Test the guardrail with intentionally invalid data to verify it's working"""
        try:
            guardrail_config = self._get_guardrail_config()
            if not guardrail_config:
                return {
                    "status": "error",
                    "message": "No guardrail configured for testing"
                }
            
            # Create VERY obvious invalid timecard data with clear mathematical errors
            invalid_test_data = """
            TIMECARD VALIDATION TEST:
            
            Employee: John Doe
            Total Wage Reported: $1000.00
            Daily Entries:
            - Day 1: $200.00
            - Day 2: $300.00
            
            MATHEMATICAL ERROR: 
            Sum of daily entries = $200 + $300 = $500
            But reported total wage = $1000
            This is clearly incorrect: $500 ≠ $1000
            
            JSON Data:
            {
                "employee_name": "John Doe",
                "employee_count": 1,
                "total_timecards": 2,
                "total_wage": 1000.0,
                "daily_entries": [
                    ["John Doe", "2025-01-15", 200.0, "Project A", "Production"],
                    ["John Doe", "2025-01-16", 300.0, "Project A", "Production"]
                ]
            }
            
            VALIDATION RESULT: This data contains mathematical errors and should be marked as INVALID.
            """
            
            logger.info(f"Testing guardrail with ID: {guardrail_config['guardrailIdentifier']}")
            
            # Test with apply_guardrail directly
            response = self.bedrock.apply_guardrail(
                guardrailIdentifier=guardrail_config["guardrailIdentifier"],
                guardrailVersion=guardrail_config.get("guardrailVersion", "DRAFT"),
                source="OUTPUT",
                content=[{"text": {"text": invalid_test_data}}]
            )
            
            action = response.get("action", "NONE")
            outputs = response.get("outputs", [])
            usage = response.get("usage", {})
            
            logger.info(f"Guardrail response action: {action}")
            logger.info(f"Usage: {usage}")
            logger.info(f"Outputs count: {len(outputs)}")
            
            # Check for automated reasoning findings
            ar_findings = []
            if outputs:
                for i, output in enumerate(outputs):
                    logger.info(f"Output {i+1} keys: {list(output.keys())}")
                    if "automatedReasoning" in output:
                        ar_data = output["automatedReasoning"]
                        findings = ar_data.get("findings", [])
                        ar_findings.extend(findings)
                        logger.info(f"Found {len(findings)} AR findings in output {i+1}")
                    else:
                        logger.info(f"No automatedReasoning in output {i+1}")
            
            # Also test with a simpler approach - just the JSON
            logger.info("Testing with simple JSON...")
            simple_json = '{"total_wage": 1000, "daily_entries": [["John", "2025-01-15", 200], ["John", "2025-01-16", 300]]}'
            
            response2 = self.bedrock.apply_guardrail(
                guardrailIdentifier=guardrail_config["guardrailIdentifier"],
                guardrailVersion=guardrail_config.get("guardrailVersion", "DRAFT"),
                source="OUTPUT",
                content=[{"text": {"text": simple_json}}]
            )
            
            action2 = response2.get("action", "NONE")
            logger.info(f"Simple JSON test action: {action2}")
            
            return {
                "status": "success",
                "test_data": invalid_test_data,
                "guardrail_action": action,
                "simple_test_action": action2,
                "automated_reasoning_findings": ar_findings,
                "expected_action": "GUARDRAIL_INTERVENED or BLOCKED",
                "test_passed": action in ["GUARDRAIL_INTERVENED", "BLOCKED"] or action2 in ["GUARDRAIL_INTERVENED", "BLOCKED"],
                "message": f"Guardrail {'WORKING' if action in ['GUARDRAIL_INTERVENED', 'BLOCKED'] else 'NOT WORKING'} - Action: {action}",
                "full_response": response,
                "usage": usage
            }
            
        except Exception as e:
            logger.error(f"Guardrail test failed: {e}")
            return {
                "status": "error",
                "message": f"Test failed: {str(e)}"
            }

    def _process_ar_findings(self, findings: List[Dict[str, Any]]) -> tuple[bool, float]:
        """Process Automated Reasoning findings and determine validation status"""
        validation_passed = True
        validation_confidence = 1.0
        
        invalid_count = 0
        satisfiable_with_errors = 0
        valid_with_errors = 0
        
        for i, finding in enumerate(findings):
            if "invalid" in finding:
                invalid_count += 1
                confidence = finding["invalid"].get("translation", {}).get("confidence", 0)
                logger.info(f"     Finding {i+1}: INVALID - {confidence} confidence")
                validation_passed = False
                validation_confidence = min(validation_confidence, 0.3)
                
            elif "satisfiable" in finding:
                confidence = finding["satisfiable"].get("translation", {}).get("confidence", 0)
                logger.info(f"     Finding {i+1}: SATISFIABLE - {confidence} confidence")
                
                # Check for mathematical errors in claims
                claims = finding["satisfiable"].get("translation", {}).get("claims", [])
                for claim in claims:
                    claim_text = claim.get("naturalLanguage", "").lower()
                    if "invalid" in claim_text or "mathematical_error" in claim_text or "false" in claim_text:
                        satisfiable_with_errors += 1
                        validation_passed = False
                        validation_confidence = min(validation_confidence, 0.6)
                        logger.info(f"       Mathematical error detected in satisfiable finding")
                        break
                        
            elif "valid" in finding:
                confidence = finding["valid"].get("translation", {}).get("confidence", 0)
                logger.info(f"     Finding {i+1}: VALID - {confidence} confidence")
                
                # Check if valid finding indicates validation failure
                claims = finding["valid"].get("translation", {}).get("claims", [])
                for claim in claims:
                    claim_text = claim.get("naturalLanguage", "").lower()
                    if ("istimecardvalid is false" in claim_text or 
                        "validation_status is equal to invalid" in claim_text or
                        "mathematical_error" in claim_text):
                        valid_with_errors += 1
                        validation_passed = False
                        validation_confidence = min(validation_confidence, 0.7)
                        logger.info(f"       Validation failure detected in valid finding")
                        break
                        
            elif "noTranslations" in finding:
                logger.info(f"     Finding {i+1}: NO_TRANSLATIONS - Complex logic detected")
                # noTranslations often indicates complex mathematical reasoning
                validation_confidence = min(validation_confidence, 0.8)
                
            else:
                logger.info(f"     Finding {i+1}: {list(finding.keys())}")
        
        # Log summary
        total_error_indicators = invalid_count + satisfiable_with_errors + valid_with_errors
        if total_error_indicators > 0:
            logger.info(f"   AR Summary: {total_error_indicators} error indicators found")
            logger.info(f"     Invalid: {invalid_count}, Satisfiable w/errors: {satisfiable_with_errors}, Valid w/errors: {valid_with_errors}")
        else:
            logger.info(f"   AR Summary: No error indicators found in {len(findings)} findings")
        
        return validation_passed, validation_confidence

    def _process_guardrail_dict(self, guardrail_trace, guardrail_findings, validation_passed, validation_confidence):
        """Process guardrail trace in dict format"""
        try:
            # Extract Automated Reasoning findings if available
            if "modelOutput" in guardrail_trace:
                model_output = guardrail_trace["modelOutput"]
                logger.debug(f"   Model output keys: {list(model_output.keys())}")
                
                if (
                    "assessments" in model_output
                    and "automatedReasoning" in model_output["assessments"]
                ):
                    ar_assessment = model_output["assessments"]["automatedReasoning"]
                    findings = ar_assessment.get("findings", [])
                    guardrail_findings.extend(findings)

                    logger.info(f"   Automated Reasoning Findings: {len(findings)} findings")
                    
                    # Process different types of findings
                    for i, finding in enumerate(findings):
                        if "invalid" in finding:
                            confidence = finding["invalid"].get("translation", {}).get("confidence", "N/A")
                            logger.info(f"     Finding {i+1}: INVALID - {confidence} confidence")
                            validation_passed = False
                            validation_confidence = 0.5
                        elif "satisfiable" in finding:
                            confidence = finding["satisfiable"].get("translation", {}).get("confidence", "N/A")
                            logger.info(f"     Finding {i+1}: SATISFIABLE - {confidence} confidence")
                            
                            # Check for mathematical errors
                            claims = finding["satisfiable"].get("translation", {}).get("claims", [])
                            for claim in claims:
                                if "INVALID" in claim.get("naturalLanguage", "") or "MATHEMATICAL_ERROR" in claim.get("naturalLanguage", ""):
                                    validation_passed = False
                                    validation_confidence = 0.6
                        else:
                            logger.info(f"     Finding {i+1}: {finding}")
                else:
                    logger.warning(f"   No Automated Reasoning assessments found in model output")
            else:
                logger.warning(f"   No model output found in guardrail trace")
        except Exception as e:
            logger.error(f"Error processing guardrail dict: {e}")

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
