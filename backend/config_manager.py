#!/usr/bin/env python3
"""
Configuration management for timecard processing system
"""

import os
import logging
from typing import Dict, Any, Optional
from database import DatabaseManager

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages application configuration with database persistence"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._init_default_settings()

    def _init_default_settings(self):
        """Initialize default settings if they don't exist"""
        defaults = {
            # Job Processing
            'max_concurrent_jobs': 3,
            'default_job_priority': 2,  # Normal
            'enable_notifications': True,
            
            # AWS Configuration
            'aws_region': 'us-west-2',
            'bedrock_model_id': 'us.anthropic.claude-sonnet-4-20250514-v1:0',
            
            # Data Management
            'auto_cleanup_enabled': True,
            'cleanup_after_days': 7,
            
            # Compliance Settings
            'federal_minimum_wage': 7.25,
            'overtime_threshold_hours': 40,
            'salary_exempt_threshold_weekly': 684,
            'max_recommended_hours_weekly': 60,
            
            # Validation Rules
            'validation_rules': {
                'daily_rate_minimum_check': True,
                'excessive_hours_flagging': True,
                'salary_exempt_validation': True,
                'human_review_triggers': True
            },
            
            # Review Triggers
            'review_triggers': {
                'rate_below_federal_minimum': True,
                'more_than_60_hours_week': True,
                'high_daily_rates_threshold': 2000,
                'salary_exempt_excessive_hours': True
            },
            
            # System Information
            'app_version': '1.0.0',
            'app_environment': 'development',
            'build_date': '2025-01-17'
        }
        
        for key, value in defaults.items():
            if self.db.get_setting(key) is None:
                self.db.set_setting(key, value)
                logger.info(f"Initialized default setting: {key} = {value}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        # First try environment variable (for sensitive data)
        env_key = key.upper().replace('.', '_')
        env_value = os.environ.get(env_key)
        if env_value is not None:
            return env_value
        
        # Then try database
        return self.db.get_setting(key, default)

    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.db.set_setting(key, value)
        logger.info(f"Updated setting: {key} = {value}")

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values"""
        settings = self.db.get_all_settings()
        
        # Override with environment variables where applicable
        env_overrides = {
            'aws_region': os.environ.get('AWS_REGION'),
            'aws_access_key_id': os.environ.get('AWS_ACCESS_KEY_ID'),
            'aws_secret_access_key': os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'bedrock_model_id': os.environ.get('BEDROCK_MODEL_ID')
        }
        
        for key, value in env_overrides.items():
            if value is not None:
                settings[key] = value
        
        return settings

    def update_multiple(self, settings: Dict[str, Any]):
        """Update multiple settings at once"""
        for key, value in settings.items():
            self.set(key, value)

    # Convenience methods for common settings
    @property
    def max_concurrent_jobs(self) -> int:
        return self.get('max_concurrent_jobs', 3)

    @property
    def default_job_priority(self) -> int:
        return self.get('default_job_priority', 2)

    @property
    def enable_notifications(self) -> bool:
        return self.get('enable_notifications', True)

    @property
    def aws_region(self) -> str:
        return self.get('aws_region', 'us-west-2')

    @property
    def bedrock_model_id(self) -> str:
        model_id = self.get('bedrock_model_id', 'us.anthropic.claude-sonnet-4-20250514-v1:0')
        logger.info(f"Config manager returning bedrock_model_id: {model_id}")
        return model_id

    @property
    def auto_cleanup_enabled(self) -> bool:
        return self.get('auto_cleanup_enabled', True)

    @property
    def cleanup_after_days(self) -> int:
        return self.get('cleanup_after_days', 7)

    @property
    def federal_minimum_wage(self) -> float:
        return self.get('federal_minimum_wage', 7.25)

    @property
    def overtime_threshold_hours(self) -> int:
        return self.get('overtime_threshold_hours', 40)

    @property
    def salary_exempt_threshold_weekly(self) -> float:
        return self.get('salary_exempt_threshold_weekly', 684)

    @property
    def max_recommended_hours_weekly(self) -> int:
        return self.get('max_recommended_hours_weekly', 60)

    @property
    def validation_rules(self) -> Dict[str, bool]:
        return self.get('validation_rules', {
            'daily_rate_minimum_check': True,
            'excessive_hours_flagging': True,
            'salary_exempt_validation': True,
            'human_review_triggers': True
        })

    @property
    def review_triggers(self) -> Dict[str, Any]:
        return self.get('review_triggers', {
            'rate_below_federal_minimum': True,
            'more_than_60_hours_week': True,
            'high_daily_rates_threshold': 2000,
            'salary_exempt_excessive_hours': True
        })

    def get_aws_credentials(self) -> Dict[str, Optional[str]]:
        """Get AWS credentials from environment"""
        return {
            'aws_access_key_id': os.environ.get('AWS_ACCESS_KEY_ID'),
            'aws_secret_access_key': os.environ.get('AWS_SECRET_ACCESS_KEY'),
            'aws_session_token': os.environ.get('AWS_SESSION_TOKEN'),
            'aws_region': self.aws_region
        }

    def validate_aws_config(self) -> Dict[str, bool]:
        """Validate AWS configuration"""
        creds = self.get_aws_credentials()
        
        return {
            'has_credentials': bool(creds['aws_access_key_id'] and creds['aws_secret_access_key']),
            'has_region': bool(creds['aws_region']),
            'bedrock_configured': bool(self.bedrock_model_id)
        }

    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        return {
            'version': self.get('app_version', '1.0.0'),
            'environment': self.get('app_environment', 'development'),
            'build_date': self.get('build_date', '2025-01-17'),
            'database_path': self.db.db_path,
            'aws_config': self.validate_aws_config()
        }