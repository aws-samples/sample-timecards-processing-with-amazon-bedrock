import React from 'react';
import {
  Box,
  SpaceBetween,
  Link
} from '@cloudscape-design/components';

const Footer = () => {
  const currentYear = new Date().getFullYear();
  
  return (
    <Box 
      padding={{ vertical: 'm', horizontal: 'l' }} 
      color="text-body-secondary"
      textAlign="center"
    >
      <SpaceBetween direction="horizontal" size="l" alignItems="center">
        <Box variant="small">
          © {currentYear} Timecard Processor
        </Box>
        <SpaceBetween direction="horizontal" size="m">
          <Link href="/settings" variant="secondary" fontSize="body-s">
            Settings
          </Link>
          <Link external href="#" variant="secondary" fontSize="body-s">
            Documentation
          </Link>
          <Link external href="#" variant="secondary" fontSize="body-s">
            Support
          </Link>
        </SpaceBetween>
        <Box variant="small">
          Built with AWS Cloudscape Design System
        </Box>
      </SpaceBetween>
    </Box>
  );
};

export default Footer;