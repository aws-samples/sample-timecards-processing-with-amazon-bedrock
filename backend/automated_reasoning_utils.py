#!/usr/bin/env python3
"""
Automated Reasoning Utilities for Timecard Validation
Helper functions for processing and formatting Automated Reasoning results
"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def extract_reasoning_findings(guardrail_response: Dict[str, Any], policy_definition: Dict[str, Any] = None) -> str:
    """
    Extract and format automated reasoning findings from guardrail response
    
    Args:
        guardrail_response: Response from apply_guardrail API
        policy_definition: Optional policy definition for enhanced formatting
    
    Returns:
        Formatted string with findings details
    """
    
    try:
        assessments = guardrail_response.get("assessments", {})
        automated_reasoning = assessments.get("automatedReasoning", {})
        findings = automated_reasoning.get("findings", [])
        
        if not findings:
            return "No automated reasoning findings available."
        
        formatted_output = []
        formatted_output.append("## Automated Reasoning Findings\n")
        
        for i, finding in enumerate(findings, 1):
            formatted_output.append(f"### Finding {i}")
            
            # Finding result
            result = finding.get("result", "UNKNOWN")
            formatted_output.append(f"**Finding Type:** {result.title()}")
            
            # Rule information
            rule_id = finding.get("ruleId", "")
            rule_description = finding.get("ruleDescription", "")
            
            if rule_id:
                formatted_output.append(f"**Rule ID:** {rule_id}")
            
            if rule_description:
                formatted_output.append(f"**Rule Description:** {rule_description}")
            
            # Variables extracted
            variables = finding.get("variables", {})
            if variables:
                formatted_output.append("**Variables Extracted:**")
                for var_name, var_value in variables.items():
                    formatted_output.append(f"  - {var_name}: {var_value}")
            
            # Suggestions
            suggestions = finding.get("suggestions", [])
            if suggestions:
                formatted_output.append("**Suggestions:**")
                for suggestion in suggestions:
                    if isinstance(suggestion, dict):
                        # Format structured suggestions
                        for key, value in suggestion.items():
                            formatted_output.append(f"  - {key}: {value}")
                    else:
                        formatted_output.append(f"  - {suggestion}")
            
            formatted_output.append("")  # Add blank line between findings
        
        return "\n".join(formatted_output)
        
    except Exception as e:
        logger.error(f"Error extracting reasoning findings: {e}")
        return f"Error processing findings: {str(e)}"


def get_policy_definition(bedrock_client, policy_arn: str) -> Dict[str, Any]:
    """
    Get policy definition from Automated Reasoning policy
    
    Args:
        bedrock_client: Boto3 Bedrock client
        policy_arn: ARN of the Automated Reasoning policy
    
    Returns:
        Policy definition dictionary
    """
    
    try:
        response = bedrock_client.export_automated_reasoning_policy_version(
            policyArn=policy_arn
        )
        return response.get('policyDefinition', {})
        
    except Exception as e:
        logger.error(f"Error getting policy definition: {e}")
        return {}


def format_validation_summary(guardrail_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format guardrail response into a validation summary
    
    Args:
        guardrail_response: Response from apply_guardrail API
    
    Returns:
        Formatted validation summary
    """
    
    try:
        action = guardrail_response.get("action", "UNKNOWN")
        assessments = guardrail_response.get("assessments", {})
        automated_reasoning = assessments.get("automatedReasoning", {})
        findings = automated_reasoning.get("findings", [])
        
        # Count findings by type
        finding_counts = {}
        compliance_issues = []
        
        for finding in findings:
            result = finding.get("result", "UNKNOWN")
            finding_counts[result] = finding_counts.get(result, 0) + 1
            
            if result in ["INVALID", "SATISFIABLE"]:
                rule_desc = finding.get("ruleDescription", "Unknown rule violation")
                compliance_issues.append(rule_desc)
        
        # Determine overall compliance status
        if action == "NONE":
            compliance_status = "COMPLIANT"
        elif action == "GUARDRAIL_INTERVENED":
            compliance_status = "REQUIRES_REVIEW"
        else:
            compliance_status = "NON_COMPLIANT"
        
        # Calculate confidence score
        confidence = 1.0
        if "INVALID" in finding_counts:
            confidence = 0.3
        elif "SATISFIABLE" in finding_counts:
            confidence = 0.7
        elif "TOO_COMPLEX" in finding_counts:
            confidence = 0.5
        
        return {
            "compliance_status": compliance_status,
            "action": action,
            "confidence_score": confidence,
            "finding_counts": finding_counts,
            "compliance_issues": compliance_issues,
            "total_findings": len(findings),
            "requires_human_review": action in ["GUARDRAIL_INTERVENED", "BLOCK"] or "SATISFIABLE" in finding_counts
        }
        
    except Exception as e:
        logger.error(f"Error formatting validation summary: {e}")
        return {
            "compliance_status": "ERROR",
            "action": "UNKNOWN",
            "confidence_score": 0.0,
            "finding_counts": {},
            "compliance_issues": [f"Error processing validation: {str(e)}"],
            "total_findings": 0,
            "requires_human_review": True
        }


def create_test_case(bedrock_client, policy_arn: str, guard_content: str, 
                    expected_result: str, query: str = None, 
                    confidence_threshold: float = None) -> Dict[str, Any]:
    """
    Create a test case for an Automated Reasoning policy
    
    Args:
        bedrock_client: Boto3 Bedrock client
        policy_arn: ARN of the policy to test
        guard_content: LLM response to validate
        expected_result: Expected validation result
        query: Optional user query
        confidence_threshold: Optional confidence threshold
    
    Returns:
        Test case creation response
    """
    
    try:
        kwargs = {
            'policyArn': policy_arn,
            'guardContent': guard_content,
            'expectedAggregatedFindingsResult': expected_result,
            'clientRequestToken': str(uuid.uuid4())
        }
        
        if query is not None:
            kwargs['query'] = query
        if confidence_threshold is not None:
            kwargs['confidenceThreshold'] = confidence_threshold
        
        response = bedrock_client.create_automated_reasoning_policy_test_case(**kwargs)
        
        logger.info(f"Created test case: {response.get('testCaseId', 'Unknown')}")
        return response
        
    except Exception as e:
        logger.error(f"Error creating test case: {e}")
        raise


def run_valid_at_n_experiment(user_query: str, initial_response: str, 
                             policy_definition: Dict[str, Any], 
                             guardrail_id: str, guardrail_version: str,
                             runtime_client, model_id: str = None,
                             max_iterations: int = 5) -> Dict[str, Any]:
    """
    Run a "Valid at N" experiment to test response rewriting
    
    Args:
        user_query: Original user query
        initial_response: Initial LLM response
        policy_definition: Automated Reasoning policy definition
        guardrail_id: Guardrail ID
        guardrail_version: Guardrail version
        runtime_client: Boto3 Bedrock runtime client
        model_id: Model ID for rewriting
        max_iterations: Maximum rewrite iterations
    
    Returns:
        Experiment results
    """
    
    if model_id is None:
        model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    
    results = {
        "query": user_query,
        "original_response": initial_response,
        "iterations": [],
        "n_value": None,
        "final_valid_response": None
    }
    
    current_response = initial_response
    
    for iteration in range(1, max_iterations + 1):
        try:
            # Apply guardrail to current response
            content_to_validate = [
                {"text": {"text": user_query, "qualifiers": ["query"]}},
                {"text": {"text": current_response, "qualifiers": ["guard_content"]}}
            ]
            
            guardrail_response = runtime_client.apply_guardrail(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=guardrail_version,
                source="OUTPUT",
                content=content_to_validate
            )
            
            # Extract findings
            findings_text = extract_reasoning_findings(guardrail_response, policy_definition)
            validation_summary = format_validation_summary(guardrail_response)
            
            iteration_data = {
                "iteration": iteration,
                "response": current_response,
                "findings": findings_text,
                "validation_summary": validation_summary,
                "action": guardrail_response.get("action", "UNKNOWN")
            }
            
            results["iterations"].append(iteration_data)
            
            # Check if valid
            if validation_summary["compliance_status"] == "COMPLIANT":
                results["n_value"] = iteration
                results["final_valid_response"] = current_response
                break
            
            # If not valid, attempt to rewrite
            if iteration < max_iterations:
                rewrite_prompt = f"""
                The following response was flagged by wage compliance validation:
                
                Original Query: {user_query}
                Current Response: {current_response}
                
                Validation Issues:
                {findings_text}
                
                Please rewrite the response to address these compliance issues while maintaining accuracy.
                """
                
                try:
                    rewrite_response = runtime_client.converse(
                        modelId=model_id,
                        messages=[{"role": "user", "content": [{"text": rewrite_prompt}]}],
                        inferenceConfig={"maxTokens": 2000, "temperature": 0.1}
                    )
                    
                    rewritten_text = rewrite_response["output"]["message"]["content"][0]["text"]
                    iteration_data["rewritten_to"] = rewritten_text
                    current_response = rewritten_text
                    
                except Exception as e:
                    logger.error(f"Failed to rewrite response: {e}")
                    break
            
        except Exception as e:
            logger.error(f"Error in iteration {iteration}: {e}")
            break
    
    if results["n_value"] is None:
        results["n_value"] = f">= {max_iterations}"
    
    return results


def display_experiment_results(results: Dict[str, Any]) -> str:
    """
    Format Valid at N experiment results for display
    
    Args:
        results: Experiment results from run_valid_at_n_experiment
    
    Returns:
        Formatted results string
    """
    
    output = []
    output.append(f"## Valid at N Experiment Results (N = {results['n_value']})")
    output.append(f"**Query:** {results['query']}")
    output.append("")
    
    output.append("### Original Response")
    output.append(results['original_response'])
    output.append("")
    
    for iteration in results['iterations']:
        output.append(f"### Iteration {iteration['iteration']}")
        output.append(f"**Action:** {iteration['action']}")
        output.append(f"**Compliance Status:** {iteration['validation_summary']['compliance_status']}")
        
        if iteration['iteration'] > 1:
            output.append("**Response:**")
            output.append(iteration['response'])
            output.append("")
        
        output.append("**Findings:**")
        output.append(iteration['findings'])
        output.append("")
        
        if 'rewritten_to' in iteration:
            output.append("**Rewritten To:**")
            output.append(iteration['rewritten_to'])
            output.append("")
    
    if results['final_valid_response'] and results['n_value'] != 1:
        output.append("### Final Valid Response")
        output.append(results['final_valid_response'])
    
    return "\n".join(output)