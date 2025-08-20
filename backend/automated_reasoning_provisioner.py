#!/usr/bin/env python3
"""
Automated Reasoning Auto-Provisioner
Automatically creates and configures Automated Reasoning Policy and Guardrails if they don't exist
"""

import boto3
import json
import uuid
import time
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)

class AutomatedReasoningProvisioner:
    """Auto-provision Automated Reasoning resources with caching and state management"""
    
    def __init__(self, region_name: str = "us-west-2", config_manager=None):
        self.region_name = region_name
        self.config_manager = config_manager
        self.bedrock_client = boto3.client('bedrock', region_name=region_name)
        self.runtime_client = boto3.client('bedrock-runtime', region_name=region_name)
        
        # Use database for state management instead of file
        if not self.config_manager:
            raise ValueError("config_manager is required for database state management")
        # Remove instance state - make it stateless
        
    # Removed _load_state and _save_state - using direct config_manager access for stateless design
    
    def _get_policy_document_hash(self) -> str:
        """Get hash of policy document to detect changes"""
        policy_doc = self._create_policy_document()
        return hashlib.md5(policy_doc.encode()).hexdigest()
    
    def _create_policy_document(self) -> str:
        """Create policy document for mathematical validation - optimized for AR detection"""
        return """
# Timecard Mathematical Validation Policy

## Purpose
This policy validates mathematical accuracy in timecard data using formal logic reasoning.

## Core Validation Logic

### Primary Rule: Sum Validation
When analyzing timecard data, verify that the reported total_wage equals the sum of all daily rates.

**Mathematical Formula:**
- total_wage = sum_of_daily_rates
- sum_of_daily_rates = daily_entries[0][2] + daily_entries[1][2] + ... + daily_entries[n][2]

**Validation Logic:**
- IF total_wage ≠ sum_of_daily_rates THEN isTimecardValid = false
- IF total_wage = sum_of_daily_rates THEN isTimecardValid = true

### Detection Examples

**Example 1 - Mathematical Error (Should detect as invalid):**
```
Input: "Total Wage: $1000, Daily entries: Day 1: $200, Day 2: $300"
Calculation: sum_daily_rates = 200 + 300 = 500
Comparison: total_wage (1000) ≠ sum_daily_rates (500)
Result: isTimecardValid = false (Mathematical inconsistency detected)
```

**Example 2 - Correct Calculation (Should detect as valid):**
```
Input: "Total Wage: $500, Daily entries: Day 1: $200, Day 2: $300"  
Calculation: sum_daily_rates = 200 + 300 = 500
Comparison: total_wage (500) = sum_daily_rates (500)
Result: isTimecardValid = true (Mathematics correct)
```

**Example 3 - Another Error Case:**
```
Input: "Total Wage: $800, Daily rates: [300, 400]"
Calculation: sum_daily_rates = 300 + 400 = 700
Comparison: total_wage (800) ≠ sum_daily_rates (700)
Result: isTimecardValid = false (Sum mismatch detected)
```

## Formal Logic Rules

### Rule 1: Sum Equality Check
```
PREMISE: total_wage = X AND sum_daily_rates = Y
CLAIM: IF X ≠ Y THEN isTimecardValid = false
CLAIM: IF X = Y THEN isTimecardValid = true
```

### Rule 2: Mathematical Consistency
```
PREMISE: daily_entries contains numeric values [a, b, c, ...]
CLAIM: sum_daily_rates = a + b + c + ...
CLAIM: IF total_wage ≠ sum_daily_rates THEN mathematical_error = true
```

### Rule 3: Validation Status
```
PREMISE: mathematical_error = true
CLAIM: isTimecardValid = false
CLAIM: validation_status = INVALID
```

## Training Examples for Automated Reasoning

**Training Case 1:**
- Input: total_wage=1000, daily_rates=[200,300]
- Expected Logic: sum_daily_rates = 500, total_wage ≠ sum_daily_rates
- Expected Result: isTimecardValid = false

**Training Case 2:**
- Input: total_wage=500, daily_rates=[200,300]  
- Expected Logic: sum_daily_rates = 500, total_wage = sum_daily_rates
- Expected Result: isTimecardValid = true

**Training Case 3:**
- Input: total_wage=1500, daily_rates=[400,500,600]
- Expected Logic: sum_daily_rates = 1500, total_wage = sum_daily_rates  
- Expected Result: isTimecardValid = true

**Training Case 4:**
- Input: total_wage=2000, daily_rates=[400,500,600]
- Expected Logic: sum_daily_rates = 1500, total_wage ≠ sum_daily_rates
- Expected Result: isTimecardValid = false

## Key Concepts for AR Training
- sum_daily_rates: The calculated sum of all daily rate values
- total_wage: The reported total wage amount
- isTimecardValid: Boolean indicating mathematical consistency
- mathematical_error: Boolean indicating calculation mismatch
- validation_status: VALID or INVALID based on mathematical checks
"""
    
    def _check_existing_resources(self) -> Tuple[bool, bool, bool]:
        """Check if policy and guardrail exist and are properly connected in AWS"""
        policy_exists = False
        guardrail_exists = False
        properly_connected = False
        
        policy_arn = self.config_manager.get('automated_reasoning_policy_arn') if self.config_manager else None
        guardrail_id = self.config_manager.get('automated_reasoning_guardrail_id') if self.config_manager else None
        
        # Check policy
        if policy_arn:
            try:
                response = self.bedrock_client.get_automated_reasoning_policy(
                    policyArn=policy_arn
                )
                policy_status = response.get("status")
                policy_exists = policy_status == "ACTIVE"
                logger.info(f"Policy check: {policy_arn} (status: {policy_status})")
                
                if not policy_exists:
                    logger.warning(f"Policy exists but not active: {policy_status}")
            except Exception as e:
                logger.warning(f"Policy not accessible in AWS: {e}")
                # Clear from database since it doesn't exist in AWS
                if self.config_manager:
                    self.config_manager.set('automated_reasoning_policy_arn', None)
                    logger.info("Cleared invalid policy ARN from database")
        
        # Check guardrail
        guardrail_response = None
        if guardrail_id:
            try:
                guardrail_response = self.bedrock_client.get_guardrail(
                    guardrailIdentifier=guardrail_id
                )
                guardrail_status = guardrail_response.get("status")
                guardrail_exists = guardrail_status == "READY"
                logger.info(f"Guardrail check: {guardrail_id} (status: {guardrail_status})")
                
                if not guardrail_exists:
                    logger.warning(f"Guardrail exists but not ready: {guardrail_status}")
            except Exception as e:
                logger.warning(f"Guardrail not accessible in AWS: {e}")
                # Clear from database since it doesn't exist in AWS
                if self.config_manager:
                    self.config_manager.set('automated_reasoning_guardrail_id', None)
                    self.config_manager.set('automated_reasoning_guardrail_version', None)
                    logger.info("Cleared invalid guardrail ID from database")
        
        # Check if they're properly connected
        if policy_exists and guardrail_exists and guardrail_response and policy_arn:
            ar_config = guardrail_response.get('automatedReasoningPolicy', {})
            attached_policies = ar_config.get('policies', [])
            
            if policy_arn in attached_policies:
                properly_connected = True
                logger.info(f"Policy properly attached to guardrail")
            else:
                logger.warning(f"Policy not attached to guardrail")
                logger.warning(f"   Expected: {policy_arn}")
                logger.warning(f"   Found: {attached_policies}")
        
        return policy_exists, guardrail_exists, properly_connected
    
    def _create_policy(self) -> str:
        """Create Automated Reasoning policy (check for existing first)"""
        
        # First check if we have a policy ARN in database
        existing_policy_arn = self.config_manager.get('automated_reasoning_policy_arn') if self.config_manager else None
        if existing_policy_arn and existing_policy_arn != 'None':
            try:
                policy_details = self.bedrock_client.get_automated_reasoning_policy(
                    policyArn=existing_policy_arn
                )
                if policy_details.get('status') == 'ACTIVE':
                    logger.info(f"Using existing policy from database: {existing_policy_arn}")
                    return existing_policy_arn
                else:
                    logger.warning(f"Policy in database not active: {policy_details.get('status')}")
            except Exception as e:
                logger.warning(f"Policy in database not accessible: {e}")
                # Clear invalid policy from database
                if self.config_manager:
                    self.config_manager.set('automated_reasoning_policy_arn', None)
        
        # Then check if we already have a policy with our naming pattern that's actually accessible
        try:
            existing_policies = self.bedrock_client.list_automated_reasoning_policies()
            for policy in existing_policies.get('policies', []):
                if policy.get('name', '').startswith('timecard-math-validation-'):
                    policy_arn = policy.get('policyArn')
                    policy_status = policy.get('status')
                    
                    # Verify the policy is actually accessible and active
                    try:
                        policy_details = self.bedrock_client.get_automated_reasoning_policy(
                            policyArn=policy_arn
                        )
                        if policy_details.get('status') == 'ACTIVE':
                            logger.info(f"Found existing active policy: {policy.get('name')} ({policy_arn})")
                            # Save to database for future use
                            if self.config_manager:
                                self.config_manager.set('automated_reasoning_policy_arn', policy_arn)
                            return policy_arn
                        else:
                            logger.info(f"Found policy but not active: {policy.get('name')} (status: {policy_status})")
                    except Exception as verify_e:
                        logger.warning(f"Policy exists in list but not accessible: {verify_e}")
                        continue
        except Exception as e:
            logger.warning(f"Failed to check existing policies: {e}")
        
        # Create new policy if none found
        policy_name = f"timecard-math-validation-{uuid.uuid4().hex[:8]}"
        description = "Mathematical validation policy for timecard data integrity"
        
        try:
            response = self.bedrock_client.create_automated_reasoning_policy(
                name=policy_name,
                description=description,
                clientRequestToken=str(uuid.uuid4())
            )
            
            policy_arn = response['policyArn']
            logger.info(f"Created new policy: {policy_name} ({policy_arn})")
            
            return policy_arn
            
        except Exception as e:
            logger.error(f"Failed to create policy: {e}")
            raise
    
    def _upload_policy_document(self, policy_arn: str) -> str:
        """Upload policy document and start build workflow"""
        try:
            document_content = self._create_policy_document()
            instructions = """
            Create a mathematical validation policy for timecard data using formal logic reasoning.
            
            Key Focus Areas:
            1. Detect sum calculation errors (total_wage ≠ sum_of_daily_rates)
            2. Use formal logic to determine isTimecardValid status
            3. Apply mathematical consistency checks
            4. Generate clear validation findings with confidence scores
            
            The policy should use automated reasoning to detect when:
            - total_wage does not equal the sum of daily rates
            - Mathematical inconsistencies exist in timecard data
            - Validation status should be marked as invalid
            
            Training should focus on mathematical logic and arithmetic validation.
            """
            
            response = self.bedrock_client.start_automated_reasoning_policy_build_workflow(
                policyArn=policy_arn,
                buildWorkflowType='INGEST_CONTENT',
                clientRequestToken=str(uuid.uuid4()),
                sourceContent={
                    'workflowContent': {
                        'documents': [{
                            'document': document_content.encode('utf-8'),
                            'documentContentType': 'txt',
                            'documentName': 'timecard_math_validation.txt',
                            'documentDescription': instructions
                        }]
                    }
                }
            )
            
            build_workflow_id = response['buildWorkflowId']
            logger.info(f"Started build workflow: {build_workflow_id}")
            
            return build_workflow_id
            
        except Exception as e:
            logger.error(f"Failed to upload policy document: {e}")
            raise
    
    def _wait_for_policy_ready(self, policy_arn: str, build_workflow_id: str, max_wait: int = 300) -> bool:
        """Wait for policy to become active"""
        start_time = time.time()
        poll_interval = 10
        
        logger.info("Waiting for policy to become active...")
        
        while time.time() - start_time < max_wait:
            try:
                # Check build workflow status
                build_response = self.bedrock_client.get_automated_reasoning_policy_build_workflow(
                    policyArn=policy_arn,
                    buildWorkflowId=build_workflow_id
                )
                
                build_status = build_response.get('status', 'UNKNOWN')
                logger.debug(f"Build status: {build_status}")
                
                if build_status == 'COMPLETED':
                    # Check if policy is active
                    try:
                        self.bedrock_client.export_automated_reasoning_policy_version(
                            policyArn=policy_arn
                        )
                        logger.info("Policy is active and ready!")
                        return True
                    except:
                        logger.debug("Build completed but policy not yet active")
                
                elif build_status in ['FAILED', 'CANCELLED']:
                    logger.error(f"Build workflow failed: {build_status}")
                    return False
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Error checking build status: {e}")
                time.sleep(poll_interval)
        
        logger.warning("Policy build timed out")
        return False
    
    def _create_guardrail(self, policy_arn: str) -> Tuple[str, str]:
        """Create guardrail with the policy attached (check for existing first)"""
        
        # First check if we have a guardrail ID in database
        existing_guardrail_id = self.config_manager.get('automated_reasoning_guardrail_id') if self.config_manager else None
        if existing_guardrail_id:
            try:
                guardrail_details = self.bedrock_client.get_guardrail(
                    guardrailIdentifier=existing_guardrail_id
                )
                if guardrail_details.get('status') == 'READY':
                    # Check if it has the right policy attached
                    ar_config = guardrail_details.get('automatedReasoningPolicyConfig', {})
                    policies = ar_config.get('policies', [])
                    if policy_arn in policies:
                        logger.info(f"Using existing guardrail from database: {existing_guardrail_id}")
                        return existing_guardrail_id, guardrail_details.get('version', 'DRAFT')
                    else:
                        logger.warning(f"Guardrail in database has different policy attached")
                else:
                    logger.warning(f"Guardrail in database not ready: {guardrail_details.get('status')}")
            except Exception as e:
                logger.warning(f"Guardrail in database not accessible: {e}")
                # Clear invalid guardrail from database
                if self.config_manager:
                    self.config_manager.set('automated_reasoning_guardrail_id', None)
        
        # Then check if we already have a guardrail with our naming pattern
        try:
            existing_guardrails = self.bedrock_client.list_guardrails()
            for guardrail in existing_guardrails.get('guardrails', []):
                if guardrail.get('name', '').startswith('timecard-math-guardrail-'):
                    guardrail_id = guardrail.get('id')
                    guardrail_status = guardrail.get('status')
                    
                    # Verify the guardrail is actually accessible and ready
                    try:
                        guardrail_details = self.bedrock_client.get_guardrail(
                            guardrailIdentifier=guardrail_id
                        )
                        if guardrail_details.get('status') == 'READY':
                            # Check if it has the right policy attached
                            ar_config = guardrail_details.get('automatedReasoningPolicyConfig', {})
                            policies = ar_config.get('policies', [])
                            if policy_arn in policies:
                                logger.info(f"Found existing compatible guardrail: {guardrail.get('name')} ({guardrail_id})")
                                # Save to database for future use
                                if self.config_manager:
                                    self.config_manager.set('automated_reasoning_guardrail_id', guardrail_id)
                                return guardrail_id, guardrail_details.get('version', 'DRAFT')
                            else:
                                logger.info(f"Found guardrail but with different policy: {guardrail.get('name')}")
                        else:
                            logger.info(f"Found guardrail but not ready: {guardrail.get('name')} (status: {guardrail_status})")
                    except Exception as verify_e:
                        logger.warning(f"Guardrail exists in list but not accessible: {verify_e}")
                        continue
        except Exception as e:
            logger.warning(f"Failed to check existing guardrails: {e}")
        
        # Create new guardrail if none found
        guardrail_name = f"timecard-math-guardrail-{uuid.uuid4().hex[:8]}"
        
        try:
            # Use exact same configuration as working guardrail 6zgrmd9ertgj
            response = self.bedrock_client.create_guardrail(
                name=guardrail_name,
                description="Mathematical validation guardrail for timecard data with Automated Reasoning",
                automatedReasoningPolicyConfig={
                    "policies": [policy_arn],
                    "confidenceThreshold": 0.3  # Same as working guardrail
                },
                crossRegionConfig={
                    'guardrailProfileIdentifier': 'us.guardrail.v1:0'
                },
                blockedInputMessaging="Input blocked due to data validation policy",
                blockedOutputsMessaging="Output blocked due to mathematical inconsistency",
                clientRequestToken=str(uuid.uuid4())
            )
            
            guardrail_id = response["guardrailId"]
            guardrail_version = response["version"]
            
            logger.info(f"Created guardrail: {guardrail_name} ({guardrail_id})")
            
            return guardrail_id, guardrail_version
            
        except Exception as e:
            logger.error(f"Failed to create guardrail: {e}")
            raise
    
    def _test_guardrail(self, guardrail_id: str, guardrail_version: str) -> bool:
        """Test the guardrail with sample data that should trigger validation errors"""
        try:
            # Test 1: Mathematical sum error (should be INVALID)
            invalid_response = """
            {
                "employee_name": "John Doe",
                "employee_count": 1,
                "total_timecards": 2,
                "total_wage": 800.0,
                "average_daily_rate": 400.0,
                "daily_entries": [
                    ["John Doe", "2025-01-15", 300.0, "Project A", "Production"],
                    ["John Doe", "2025-01-16", 400.0, "Project A", "Production"]
                ]
            }
            """
            
            response1 = self.runtime_client.apply_guardrail(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=guardrail_version,
                source="OUTPUT",
                content=[{"text": {"text": invalid_response}}]
            )
            
            action1 = response1.get("action", "NONE")
            logger.info(f"Test 1 (Invalid sum - should block): {action1}")
            
            # Test 2: Valid data (should pass)
            valid_response = """
            {
                "employee_name": "Jane Smith",
                "employee_count": 1,
                "total_timecards": 2,
                "total_wage": 700.0,
                "average_daily_rate": 350.0,
                "daily_entries": [
                    ["Jane Smith", "2025-01-15", 300.0, "Project B", "Audio"],
                    ["Jane Smith", "2025-01-16", 400.0, "Project B", "Audio"]
                ]
            }
            """
            
            response2 = self.runtime_client.apply_guardrail(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=guardrail_version,
                source="OUTPUT",
                content=[{"text": {"text": valid_response}}]
            )
            
            action2 = response2.get("action", "NONE")
            logger.info(f"Test 2 (Valid data - should pass): {action2}")
            
            # Test 3: Count mismatch (should be INVALID)
            count_error_response = """
            {
                "employee_name": "Bob Wilson",
                "employee_count": 2,
                "total_timecards": 5,
                "total_wage": 600.0,
                "average_daily_rate": 300.0,
                "daily_entries": [
                    ["Bob Wilson", "2025-01-15", 300.0, "Project C", "Video"],
                    ["Bob Wilson", "2025-01-16", 300.0, "Project C", "Video"]
                ]
            }
            """
            
            response3 = self.runtime_client.apply_guardrail(
                guardrailIdentifier=guardrail_id,
                guardrailVersion=guardrail_version,
                source="OUTPUT",
                content=[{"text": {"text": count_error_response}}]
            )
            
            action3 = response3.get("action", "NONE")
            logger.info(f"Test 3 (Count mismatch - should block): {action3}")
            
            # Analyze results
            tests_passed = 0
            if action1 in ["GUARDRAIL_INTERVENED", "BLOCKED"]:
                tests_passed += 1
                logger.info("✓ Test 1 PASSED: Invalid sum correctly blocked")
            else:
                logger.warning("✗ Test 1 FAILED: Invalid sum not blocked")
                
            if action2 == "NONE":
                tests_passed += 1
                logger.info("✓ Test 2 PASSED: Valid data correctly allowed")
            else:
                logger.warning("✗ Test 2 FAILED: Valid data incorrectly blocked")
                
            if action3 in ["GUARDRAIL_INTERVENED", "BLOCKED"]:
                tests_passed += 1
                logger.info("✓ Test 3 PASSED: Count mismatch correctly blocked")
            else:
                logger.warning("✗ Test 3 FAILED: Count mismatch not blocked")
            
            success_rate = tests_passed / 3
            logger.info(f"Guardrail test results: {tests_passed}/3 tests passed ({success_rate:.1%})")
            
            return tests_passed >= 2  # At least 2/3 tests should pass
            
        except Exception as e:
            logger.error(f"Guardrail test failed: {e}")
            return False
    
    def _update_config(self, policy_arn: str, guardrail_id: str, guardrail_version: str):
        """Update configuration manager with new values"""
        if self.config_manager:
            try:
                self.config_manager.set('automated_reasoning_policy_arn', policy_arn)
                self.config_manager.set('automated_reasoning_guardrail_id', guardrail_id)
                self.config_manager.set('automated_reasoning_guardrail_version', guardrail_version)
                logger.info("Updated configuration with new Automated Reasoning settings")
            except Exception as e:
                logger.error(f"Failed to update configuration: {e}")
    
    def ensure_provisioned(self, force_recreate: bool = False) -> Dict[str, Any]:
        """
        Ensure Automated Reasoning resources are provisioned with distributed locking
        
        Args:
            force_recreate: Force recreation of resources even if they exist
            
        Returns:
            Dict with policy_arn, guardrail_id, guardrail_version, and status
        """
        try:
            logger.info("Checking Automated Reasoning status...")
            
            # Use distributed lock to prevent race conditions
            lock_key = 'automated_reasoning_provisioning_lock'
            lock_acquired = self._acquire_distributed_lock(lock_key)
            
            if not lock_acquired:
                logger.info("Another instance is provisioning, checking current status...")
                # Wait a bit and check current status
                time.sleep(2)
                return self._get_current_status()
            
            try:
                # Check current status from config (inside lock)
                current_status = self.config_manager.get('automated_reasoning_status', 'not_configured') if self.config_manager else 'not_configured'
                policy_arn = self.config_manager.get('automated_reasoning_policy_arn') if self.config_manager else None
                guardrail_id = self.config_manager.get('automated_reasoning_guardrail_id') if self.config_manager else None
                build_workflow_id = self.config_manager.get('automated_reasoning_build_workflow_id') if self.config_manager else None
                
                logger.info(f"Current status: {current_status}")
                logger.info(f"   Policy ARN: {policy_arn or 'None'}")
                logger.info(f"   Guardrail ID: {guardrail_id or 'None'}")
                
                # Always verify resources exist in AWS and are properly connected
                if current_status == 'ready' and not force_recreate:
                    logger.info("Verifying existing resources in AWS...")
                    try:
                        # Check if we have the required IDs
                        if not policy_arn or not guardrail_id:
                            logger.warning("Missing policy ARN or guardrail ID in database")
                            # Before starting fresh, check if there are existing resources we can use
                            policy_exists, guardrail_exists, properly_connected = self._check_existing_resources()
                            if policy_exists or guardrail_exists:
                                logger.info("Found existing resources, attempting to use them...")
                                return self._get_current_status()
                            logger.info("No existing resources found, starting fresh provisioning...")
                            return self._start_async_creation()
                        
                        # Verify policy exists and is active
                        try:
                            policy_response = self.bedrock_client.get_automated_reasoning_policy(
                                policyArn=policy_arn
                            )
                            policy_status = policy_response.get("status")
                            if policy_status != "ACTIVE":
                                logger.warning(f"Policy exists but not active: {policy_status}")
                                return self._start_async_creation()
                        except Exception as e:
                            logger.warning(f"Policy not accessible: {e}")
                            return self._start_async_creation()
                        
                        # Verify guardrail exists and is ready
                        try:
                            guardrail_response = self.bedrock_client.get_guardrail(
                                guardrailIdentifier=guardrail_id
                            )
                            guardrail_status = guardrail_response.get("status")
                            if guardrail_status != "READY":
                                logger.warning(f"Guardrail exists but not ready: {guardrail_status}")
                                return self._start_async_creation()
                        except Exception as e:
                            logger.warning(f"Guardrail not accessible: {e}")
                            return self._start_async_creation()
                        
                        # Verify guardrail has the policy attached
                        ar_config = guardrail_response.get('automatedReasoningPolicy', {})
                        attached_policies = ar_config.get('policies', [])
                        
                        if policy_arn not in attached_policies:
                            logger.warning(f"Policy not attached to guardrail")
                            logger.warning(f"   Expected: {policy_arn}")
                            logger.warning(f"   Found: {attached_policies}")
                            return self._start_async_creation()
                        
                        # All checks passed - resources are properly configured
                        logger.info("Automated Reasoning READY - All resources verified")
                        logger.info(f"   Policy: {policy_arn} (status: {policy_status})")
                        logger.info(f"   Guardrail: {guardrail_id} (status: {guardrail_status})")
                        logger.info(f"   Policy properly attached to guardrail")
                        
                        return {
                            "policy_arn": policy_arn,
                            "guardrail_id": guardrail_id,
                            "guardrail_version": self.config_manager.get('automated_reasoning_guardrail_version', 'DRAFT'),
                            "status": "ready",
                            "created": False,
                            "verified": True
                        }
                        
                    except Exception as e:
                        logger.error(f"Failed to verify resources: {e}")
                        logger.info("Starting fresh provisioning due to verification failure...")
                        return self._start_async_creation()
                
                # If currently creating, check progress
                if current_status == 'creating' and policy_arn and build_workflow_id:
                    logger.info("Automated Reasoning CREATING - Checking progress...")
                    logger.info(f"   Policy: {policy_arn}")
                    logger.info(f"   Build Workflow: {build_workflow_id}")
                    return self._check_creation_progress(policy_arn, build_workflow_id)
                
                # If failed or not configured, start creation
                if current_status in ['not_configured', 'failed'] or force_recreate:
                    logger.info(f"Starting Automated Reasoning creation (reason: {current_status})")
                    if force_recreate:
                        logger.info("   Force recreate requested")
                    return self._start_async_creation()
                
                # Default fallback
                return self._get_current_status()
                
            finally:
                self._release_distributed_lock(lock_key)
            
        except Exception as e:
            logger.error(f"Automated Reasoning check failed: {e}")
            if self.config_manager:
                self.config_manager.set('automated_reasoning_status', 'failed')
            return {
                "policy_arn": None,
                "guardrail_id": None,
                "guardrail_version": None,
                "status": "failed",
                "created": False,
                "error": str(e)
            }

    def _start_async_creation(self) -> Dict[str, Any]:
        """Start asynchronous creation of Automated Reasoning resources"""
        try:
            logger.info("Starting Automated Reasoning creation process...")
            
            # First check if there are already existing resources we can use
            policy_exists, guardrail_exists, properly_connected = self._check_existing_resources()
            if policy_exists and guardrail_exists and properly_connected:
                logger.info("Found fully configured resources, using existing setup")
                return self._get_current_status()
            
            # Check if we have partial resources and clean them up
            existing_policy_arn = self.config_manager.get('automated_reasoning_policy_arn') if self.config_manager else None
            existing_guardrail_id = self.config_manager.get('automated_reasoning_guardrail_id') if self.config_manager else None
            existing_build_workflow_id = self.config_manager.get('automated_reasoning_build_workflow_id') if self.config_manager else None
            
            logger.info(f"Existing resources - Policy: {existing_policy_arn}, Guardrail: {existing_guardrail_id}, Workflow: {existing_build_workflow_id}")
            
            # If we have an ongoing build workflow, don't create new resources
            if existing_policy_arn and existing_build_workflow_id:
                logger.info("Found existing policy and build workflow, checking status...")
                try:
                    build_response = self.bedrock_client.get_automated_reasoning_policy_build_workflow(
                        policyArn=existing_policy_arn,
                        buildWorkflowId=existing_build_workflow_id
                    )
                    build_status = build_response.get('status', 'UNKNOWN')
                    logger.info(f"Existing build workflow status: {build_status}")
                    
                    if build_status in ['BUILDING', 'QUEUED']:
                        logger.info("Build workflow still in progress, not creating new resources")
                        return {
                            "policy_arn": existing_policy_arn,
                            "guardrail_id": None,
                            "guardrail_version": None,
                            "status": "creating",
                            "created": False,
                            "build_workflow_id": existing_build_workflow_id,
                            "message": f"Build workflow in progress: {build_status}"
                        }
                except Exception as e:
                    logger.warning(f"Failed to check existing build workflow: {e}")
            
            if existing_policy_arn or existing_guardrail_id:
                logger.info("Found partial resources, verifying before cleanup...")
                policy_exists, guardrail_exists, properly_connected = self._check_existing_resources()
                
                # If we have a valid policy but no guardrail, try to use the existing policy
                if policy_exists and not guardrail_exists:
                    logger.info("Found valid policy, will create guardrail for it")
                    policy_arn = existing_policy_arn
                    
                    # Check if policy is ready for guardrail creation
                    try:
                        # Try to export policy to see if it's ready
                        self.bedrock_client.export_automated_reasoning_policy_version(
                            policyArn=policy_arn
                        )
                        logger.info("Policy is ready, creating guardrail...")
                        guardrail_id, guardrail_version = self._create_guardrail(policy_arn)
                        
                        # Update config to ready status
                        if self.config_manager:
                            ready_settings = {
                                'automated_reasoning_status': 'ready',
                                'automated_reasoning_guardrail_id': guardrail_id,
                                'automated_reasoning_guardrail_version': guardrail_version,
                                'automated_reasoning_last_check': time.time(),
                                'automated_reasoning_build_workflow_id': None  # Clear workflow ID
                            }
                            if hasattr(self.config_manager, 'update_multiple'):
                                self.config_manager.update_multiple(ready_settings)
                            else:
                                for key, value in ready_settings.items():
                                    self.config_manager.set(key, value)
                        
                        return {
                            "policy_arn": policy_arn,
                            "guardrail_id": guardrail_id,
                            "guardrail_version": guardrail_version,
                            "status": "ready",
                            "created": True,
                            "message": "Automated Reasoning setup completed using existing policy!"
                        }
                    except Exception as e:
                        logger.warning(f"Policy not ready for guardrail creation: {e}")
                        # Policy exists but not ready, we'll need to wait or recreate
            
            # Step 1: Create policy (this will reuse existing if available)
            logger.info("Creating/finding Automated Reasoning policy...")
            policy_arn = self._create_policy()
            logger.info(f"Policy ready: {policy_arn}")
            
            # Step 2: Start document upload (async operation)
            logger.info("Starting policy document upload...")
            build_workflow_id = self._upload_policy_document(policy_arn)
            logger.info(f"Build workflow started: {build_workflow_id}")
            
            # Update config with creation status atomically
            if self.config_manager:
                creation_settings = {
                    'automated_reasoning_status': 'creating',
                    'automated_reasoning_policy_arn': policy_arn,
                    'automated_reasoning_build_workflow_id': build_workflow_id,
                    'automated_reasoning_created_at': time.time(),
                    'automated_reasoning_last_check': time.time()
                }
                # Use bulk update if available, otherwise individual updates
                if hasattr(self.config_manager, 'update_multiple'):
                    self.config_manager.update_multiple(creation_settings)
                else:
                    for key, value in creation_settings.items():
                        self.config_manager.set(key, value)
            
            return {
                "policy_arn": policy_arn,
                "guardrail_id": None,
                "guardrail_version": None,
                "status": "creating",
                "created": True,
                "build_workflow_id": build_workflow_id,
                "message": "Policy creation started. Guardrail will be created when policy is ready."
            }
            
        except Exception as e:
            logger.error(f"Failed to start creation: {e}")
            if self.config_manager:
                self.config_manager.set('automated_reasoning_status', 'failed')
            raise

    def _check_creation_progress(self, policy_arn: str, build_workflow_id: str) -> Dict[str, Any]:
        """Check progress of ongoing creation"""
        try:
            # Check build workflow status
            build_response = self.bedrock_client.get_automated_reasoning_policy_build_workflow(
                policyArn=policy_arn,
                buildWorkflowId=build_workflow_id
            )
            
            build_status = build_response.get('status', 'UNKNOWN')
            logger.info(f"Build workflow status: {build_status}")
            
            if build_status == 'COMPLETED':
                # Policy is ready, create guardrail
                logger.info("Policy is ready, creating guardrail...")
                try:
                    guardrail_id, guardrail_version = self._create_guardrail(policy_arn)
                    logger.info(f"Guardrail created: {guardrail_id}")
                    
                    # Update config to ready status atomically
                    if self.config_manager:
                        ready_settings = {
                            'automated_reasoning_status': 'ready',
                            'automated_reasoning_guardrail_id': guardrail_id,
                            'automated_reasoning_guardrail_version': guardrail_version,
                            'automated_reasoning_last_check': time.time(),
                            'automated_reasoning_build_workflow_id': None  # Clear workflow ID since it's completed
                        }
                        logger.info(f"Updating DB to ready status with guardrail: {guardrail_id}")
                        if hasattr(self.config_manager, 'update_multiple'):
                            self.config_manager.update_multiple(ready_settings)
                        else:
                            for key, value in ready_settings.items():
                                self.config_manager.set(key, value)
                        logger.info("DB successfully updated to ready status")
                    
                    return {
                        "policy_arn": policy_arn,
                        "guardrail_id": guardrail_id,
                        "guardrail_version": guardrail_version,
                        "status": "ready",
                        "created": True,
                        "message": "Automated Reasoning setup completed successfully!"
                    }
                    
                except Exception as e:
                    logger.error(f"Failed to create guardrail: {e}")
                    if self.config_manager:
                        self.config_manager.set('automated_reasoning_status', 'failed')
                    raise
                    
            elif build_status in ['FAILED', 'CANCELLED']:
                logger.error(f"Build workflow failed: {build_status}")
                if self.config_manager:
                    self.config_manager.set('automated_reasoning_status', 'failed')
                return {
                    "policy_arn": policy_arn,
                    "guardrail_id": None,
                    "guardrail_version": None,
                    "status": "failed",
                    "created": False,
                    "error": f"Build workflow {build_status.lower()}"
                }
            else:
                # Still in progress
                if self.config_manager:
                    self.config_manager.set('automated_reasoning_last_check', time.time())
                
                return {
                    "policy_arn": policy_arn,
                    "guardrail_id": None,
                    "guardrail_version": None,
                    "status": "creating",
                    "created": False,
                    "build_status": build_status,
                    "message": f"Policy build in progress: {build_status}"
                }
                
        except Exception as e:
            logger.error(f"Failed to check creation progress: {e}")
            if self.config_manager:
                self.config_manager.set('automated_reasoning_status', 'failed')
            return {
                "policy_arn": policy_arn,
                "guardrail_id": None,
                "guardrail_version": None,
                "status": "failed",
                "created": False,
                "error": str(e)
            }
    
    def _acquire_distributed_lock(self, lock_key: str, timeout: int = 30) -> bool:
        """Acquire distributed lock using database"""
        try:
            if not self.config_manager:
                return True  # Fallback to no locking
            
            # Use database as distributed lock with timestamp
            lock_value = {
                "locked_by": f"{uuid.uuid4().hex[:8]}",
                "locked_at": time.time(),
                "expires_at": time.time() + timeout
            }
            
            # Check if lock exists and is not expired
            existing_lock = self.config_manager.get(lock_key)
            if existing_lock and isinstance(existing_lock, dict):
                if existing_lock.get('expires_at', 0) > time.time():
                    logger.info(f"Lock {lock_key} is held by another instance")
                    return False
            
            # Acquire lock
            self.config_manager.set(lock_key, lock_value)
            logger.info(f"Acquired distributed lock: {lock_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to acquire distributed lock: {e}")
            return False
    
    def _release_distributed_lock(self, lock_key: str):
        """Release distributed lock"""
        try:
            if self.config_manager:
                self.config_manager.set(lock_key, None)
                logger.info(f"Released distributed lock: {lock_key}")
        except Exception as e:
            logger.error(f"Failed to release distributed lock: {e}")
    
    def _clear_all_settings(self):
        """Atomically clear all automated reasoning settings"""
        if self.config_manager:
            settings_to_clear = [
                'automated_reasoning_status',
                'automated_reasoning_policy_arn',
                'automated_reasoning_guardrail_id',
                'automated_reasoning_guardrail_version',
                'automated_reasoning_build_workflow_id',
                'automated_reasoning_created_at',
                'automated_reasoning_last_check'
            ]
            
            for setting in settings_to_clear:
                self.config_manager.set(setting, None)
    
    def _get_current_status(self) -> Dict[str, Any]:
        """Get current status without side effects (stateless)"""
        if not self.config_manager:
            return {
                "policy_arn": None,
                "guardrail_id": None,
                "guardrail_version": None,
                "status": "not_configured",
                "created": False
            }
        
        policy_arn = self.config_manager.get('automated_reasoning_policy_arn')
        guardrail_id = self.config_manager.get('automated_reasoning_guardrail_id')
        status = self.config_manager.get('automated_reasoning_status', 'not_configured')
        
        return {
            "policy_arn": policy_arn,
            "guardrail_id": guardrail_id,
            "guardrail_version": self.config_manager.get('automated_reasoning_guardrail_version', 'DRAFT'),
            "status": status,
            "created": False
        }

    def _get_current_status_with_smart_check(self) -> Dict[str, Any]:
        """Get current status with minimal AWS API calls for UI display"""
        if not self.config_manager:
            return self._get_current_status()
        
        current_status = self.config_manager.get('automated_reasoning_status', 'not_configured')
        
        # For UI display, don't make AWS API calls - just return cached status
        # Progress checking should be done via dedicated endpoint or background process
        base_status = self._get_current_status()
        
        # Add additional info for 'creating' status
        if current_status == 'creating':
            build_workflow_id = self.config_manager.get('automated_reasoning_build_workflow_id')
            last_check = self.config_manager.get('automated_reasoning_last_check', 0)
            
            base_status.update({
                "message": "Policy build in progress",
                "build_workflow_id": build_workflow_id,
                "last_check": last_check
            })
        
        return base_status

    def get_current_config(self) -> Dict[str, Any]:
        """Get current Automated Reasoning configuration from database (stateless)"""
        if not self.config_manager:
            return {
                "policy_arn": None,
                "guardrail_id": None,
                "guardrail_version": None,
                "is_provisioned": False,
                "created_at": None,
                "last_verified": None
            }
        
        policy_arn = self.config_manager.get('automated_reasoning_policy_arn')
        guardrail_id = self.config_manager.get('automated_reasoning_guardrail_id')
        
        return {
            "policy_arn": policy_arn,
            "guardrail_id": guardrail_id,
            "guardrail_version": self.config_manager.get('automated_reasoning_guardrail_version', 'DRAFT'),
            "is_provisioned": bool(policy_arn and guardrail_id),
            "created_at": self.config_manager.get('automated_reasoning_created_at'),
            "last_verified": self.config_manager.get('automated_reasoning_last_check'),
            "status": self.config_manager.get('automated_reasoning_status', 'not_configured')
        }


def auto_provision_if_needed(config_manager=None, region_name: str = "us-west-2") -> Dict[str, Any]:
    """
    Convenience function to auto-provision Automated Reasoning if needed
    
    Returns:
        Configuration dict with policy_arn, guardrail_id, etc.
    """
    provisioner = AutomatedReasoningProvisioner(region_name, config_manager)
    
    try:
        result = provisioner.ensure_provisioned()
        
        if result["created"]:
            logger.info("Automated Reasoning has been automatically provisioned!")
            logger.info(f"Policy ARN: {result['policy_arn']}")
            logger.info(f"Guardrail ID: {result['guardrail_id']}")
        else:
            logger.info("Automated Reasoning is already configured and ready")
        
        return result
        
    except Exception as e:
        logger.error(f"Auto-provisioning failed: {e}")
        logger.info("System will fall back to basic validation")
        return {
            "policy_arn": None,
            "guardrail_id": None,
            "guardrail_version": None,
            "status": "failed",
            "created": False,
            "error": str(e)
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = auto_provision_if_needed()
    print(json.dumps(result, indent=2))