import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import '@cloudscape-design/global-styles/index.css';
import './App.css';

// Cloudscape Components
import {
  AppLayout,
  TopNavigation,
  SideNavigation,
  ContentLayout,
  Flashbar
} from '@cloudscape-design/components';
import { I18nProvider } from '@cloudscape-design/components/i18n';
import messages from '@cloudscape-design/components/i18n/messages/all.en';

// Components
import { Breadcrumbs } from './components/Breadcrumbs';

// Pages
import Dashboard from './pages/Dashboard';
import JobsTable from './pages/JobsTable';
import JobDetails from './pages/JobDetails';
import UploadPage from './pages/UploadPage';
import ReviewQueue from './pages/ReviewQueue';
import Settings from './pages/Settings';

// Services
import { jobService } from './services/jobService';

function AppContent() {
  const navigate = useNavigate();
  const location = useLocation();
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [notifications, setNotifications] = useState([]);
  const [queueStats, setQueueStats] = useState({});

  // Poll for queue stats
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const stats = await jobService.getQueueStats();
        setQueueStats(stats);
      } catch (error) {
        console.error('Failed to fetch queue stats:', error);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const addNotification = (notification) => {
    const id = Date.now().toString();
    setNotifications(prev => [...prev, { ...notification, id }]);

    // Auto-remove after 5 seconds
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 5000);
  };

  const removeNotification = (id) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const navigationItems = [
    { type: 'link', text: 'Dashboard', href: '/dashboard' },
    {
      type: 'section',
      text: 'Processing',
      items: [
        { type: 'link', text: 'Upload Files', href: '/upload' },
        { type: 'link', text: 'Jobs', href: '/jobs' },
        {
          type: 'link',
          text: 'Review Queue',
          href: '/review',
          info: queueStats.review_queue > 0 ? `${queueStats.review_queue} pending` : undefined
        }
      ]
    },
    {
      type: 'section',
      text: 'Administration',
      items: [
        { type: 'link', text: 'Settings', href: '/settings' }
      ]
    }
  ];



  function getActiveHref(pathname) {
    // For job details pages, highlight the Jobs menu item
    if (pathname.startsWith('/jobs/')) {
      return '/jobs';
    }
    return pathname;
  }

  return (
    <div id="app" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopNavigation
        identity={{
          href: '/',
          title: 'Timecard Processor'
        }}
        utilities={[
          {
            type: 'button',
            iconName: 'status-info',
            text: `${queueStats.total_jobs || 0} Total`,
            variant: 'normal',
            title: 'Total jobs in system'
          },
          {
            type: 'button',
            iconName: 'status-in-progress',
            text: `${queueStats.processing || 0} Processing`,
            variant: queueStats.processing > 0 ? 'primary' : 'normal',
            title: 'Currently processing jobs'
          },
          {
            type: 'button',
            iconName: 'status-negative',
            text: `${queueStats.failed || 0} Failed`,
            variant: queueStats.failed > 0 ? 'error' : 'normal',
            title: 'Failed jobs requiring attention'
          },
          {
            type: 'button',
            iconName: 'refresh',
            ariaLabel: 'Refresh status',
            onClick: () => window.location.reload(),
            title: 'Refresh page'
          },
          {
            type: 'menu-dropdown',
            iconName: 'settings',
            text: 'Admin',
            items: [
              {
                id: 'cleanup',
                text: 'Cleanup Old Jobs',
                iconName: 'remove'
              },
              {
                id: 'settings',
                text: 'Settings',
                iconName: 'settings'
              },
              {
                id: 'divider',
                type: 'divider'
              },
              {
                id: 'help',
                text: 'Help & Documentation',
                iconName: 'external',
                external: true,
                href: '#'
              }
            ],
            onItemClick: ({ detail }) => {
              if (detail.id === 'settings') {
                navigate('/settings');
              } else if (detail.id === 'cleanup') {
                // Handle cleanup action
                console.log('Cleanup requested');
              }
            }
          }
        ]}
      />

      <div style={{ flex: 1 }}>
        <AppLayout
          contentType="default"
          navigationOpen={navigationOpen}
          onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
          toolsHide={true}
          navigation={
            <SideNavigation
              activeHref={getActiveHref(location.pathname)}
              header={{
                href: '/dashboard',
                text: 'Timecard Processor'
              }}
              onFollow={(event) => {
                if (!event.detail.external) {
                  event.preventDefault();
                  navigate(event.detail.href);
                }
              }}
              items={navigationItems}
            />
          }
          breadcrumbs={<Breadcrumbs />}
          notifications={
            <Flashbar items={notifications.map(notification => ({
              ...notification,
              onDismiss: () => removeNotification(notification.id)
            }))} />
          }
          content={
            <ContentLayout>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route
                  path="/dashboard"
                  element={<Dashboard addNotification={addNotification} />}
                />
                <Route
                  path="/upload"
                  element={<UploadPage addNotification={addNotification} />}
                />
                <Route
                  path="/jobs"
                  element={<JobsTable addNotification={addNotification} />}
                />
                <Route
                  path="/jobs/:jobId"
                  element={<JobDetails addNotification={addNotification} />}
                />
                <Route
                  path="/review"
                  element={<ReviewQueue addNotification={addNotification} />}
                />
                <Route
                  path="/settings"
                  element={<Settings addNotification={addNotification} />}
                />
              </Routes>
            </ContentLayout>
          }
        />
      </div>
    </div>
  );
}

function App() {
  return (
    <I18nProvider locale="en" messages={[messages]}>
      <Router>
        <AppContent />
      </Router>
    </I18nProvider>
  );
}

export default App;