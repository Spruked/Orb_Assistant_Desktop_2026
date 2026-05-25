const { ChakraProvider, Box, Flex, Heading, Text, Button, VStack, HStack, Badge, Spinner, Tabs, TabList, TabPanels, Tab, TabPanel, SimpleGrid, Stat, StatLabel, StatNumber, Textarea } = ChakraUIReact;
const { useState, useEffect } = React;

function CoreCard({ name, status, onRestart }) {
  const statusColor = {
    running: 'green',
    starting: 'yellow',
    stopped: 'red',
    crashed: 'red'
  }[status] || 'gray';

  const icon = status === 'running' ? '✅' : status === 'starting' ? '⏳' : '❌';

  return React.createElement(Box, {
    p: 5,
    bg: 'gray.800',
    borderRadius: 'lg',
    border: '1px solid',
    borderColor: `${statusColor}.600`,
    _hover: { borderColor: 'cyan.500' }
  },
    React.createElement(HStack, { justify: 'space-between', mb: 3 },
      React.createElement(Heading, { size: 'sm', textTransform: 'uppercase' }, name),
      React.createElement(Badge, { colorScheme: statusColor }, status)
    ),
    React.createElement(Text, { fontSize: '2xl', textAlign: 'center', my: 4 }, icon),
    React.createElement(Button, {
      size: 'sm',
      colorScheme: 'teal',
      onClick: () => onRestart(name),
      isDisabled: status === 'starting'
    }, 'Restart')
  );
}

function CALIDashboard() {
  const [systemStatus, setSystemStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [query, setQuery] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [response, setResponse] = useState(null);
  const [shutdownInitiated, setShutdownInitiated] = useState(false);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const status = await window.caliAPI.getSystemStatus();
        setSystemStatus(status);
      } catch (err) {
        console.error('Status poll failed:', err);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const logHandler = (log) => {
      setLogs((prev) => [...prev.slice(-99), log]);
    };
    window.caliAPI.onCaliLog(logHandler);
    return () => window.caliAPI.removeAllListeners('cali-log');
  }, []);

  useEffect(() => {
    const shutdownHandler = () => setShutdownInitiated(true);
    window.caliAPI.onAppShutdown(shutdownHandler);
    return () => window.caliAPI.removeAllListeners('app-shutdown');
  }, []);

  const handleQuery = async () => {
    if (!query.trim() || isProcessing) return;
    setIsProcessing(true);
    setResponse(null);
    try {
      const result = await window.caliAPI.queryCali(query);
      setResponse(result);
    } catch (error) {
      console.error('Query failed:', error);
      setLogs((prev) => [...prev, { level: 'error', text: `Query error: ${error.message}`, timestamp: Date.now() }]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRestartCore = async (coreName) => {
    try {
      await window.caliAPI.restartCore(coreName);
    } catch (error) {
      console.error(`Failed to restart ${coreName}:`, error);
    }
  };

  const handleEmergencyStop = () => {
    if (confirm('Emergency stop will terminate all cores immediately. Continue?')) {
      window.caliAPI.stopAll();
    }
  };

  const getSystemHealth = () => {
    if (!systemStatus) return 'initializing';
    if (systemStatus.healthy) return 'healthy';
    return 'degraded';
  };

  const healthColor = {
    healthy: 'green',
    degraded: 'yellow',
    initializing: 'gray'
  }[getSystemHealth()];

  return React.createElement(ChakraProvider, null,
    React.createElement(Box, { p: 6, bg: 'gray.900', minH: '100vh' },
      React.createElement(Flex, { justify: 'space-between', align: 'center', mb: 6 },
        React.createElement(Heading, { size: 'xl', color: 'cyan.400' }, 'CALI UCM_4_Core v2.1'),
        React.createElement(HStack, null,
          React.createElement(Badge, { colorScheme: healthColor, fontSize: 'lg', px: 3, py: 1 }, getSystemHealth().toUpperCase()),
          React.createElement(Button, { colorScheme: 'red', size: 'sm', onClick: handleEmergencyStop, isDisabled: shutdownInitiated }, 'Emergency Stop')
        )
      ),

      React.createElement(SimpleGrid, { columns: { base: 2, md: 5 }, spacing: 5, mb: 6 },
        systemStatus ? Object.entries(systemStatus.cores).map(([name, status]) =>
          React.createElement(CoreCard, { key: name, name: name.replace('_', ' ').toUpperCase(), status, onRestart: handleRestartCore })
        ) : Array(5).fill().map((_, i) => React.createElement(Spinner, { key: i, size: 'xl', color: 'cyan.500' }))
      ),

      React.createElement(Tabs, { variant: 'enclosed', colorScheme: 'cyan' },
        React.createElement(TabList, null,
          React.createElement(Tab, null, '🧠 Query'),
          React.createElement(Tab, null, '📊 Metrics'),
          React.createElement(Tab, null, '📜 Logs')
        ),
        React.createElement(TabPanels, null,
          React.createElement(TabPanel, null,
            React.createElement(SimpleGrid, { columns: { base: 1, lg: 2 }, spacing: 6 },
              React.createElement(VStack, { align: 'stretch' },
                React.createElement(Textarea, {
                  placeholder: 'Enter query for CALI orchestrator...',
                  value: query,
                  onChange: (e) => setQuery(e.target.value),
                  minH: '150px',
                  bg: 'gray.800',
                  color: 'white',
                  border: '1px solid',
                  borderColor: 'gray.700'
                }),
                React.createElement(Button, {
                  colorScheme: 'cyan',
                  size: 'lg',
                  onClick: handleQuery,
                  isLoading: isProcessing,
                  loadingText: 'Processing...',
                  isDisabled: shutdownInitiated || !systemStatus?.healthy
                }, 'Execute Query')
              ),
              response && React.createElement(VStack, { align: 'stretch' },
                React.createElement(Heading, { size: 'md', mb: 3 }, 'Response'),
                React.createElement(Box, { bg: 'gray.800', p: 4, borderRadius: 'md', minH: '200px' },
                  React.createElement(Text, { whiteSpace: 'pre-wrap' }, response.text || JSON.stringify(response, null, 2))
                )
              )
            )
          ),
          React.createElement(TabPanel, null,
            React.createElement(SimpleGrid, { columns: { base: 1, md: 3 }, spacing: 6 },
              React.createElement(Stat, null,
                React.createElement(StatLabel, null, 'Active Threads'),
                React.createElement(StatNumber, null, systemStatus?.active_threads || 0)
              ),
              React.createElement(Stat, null,
                React.createElement(StatLabel, null, 'Memory Consolidation Queue'),
                React.createElement(StatNumber, null, systemStatus?.consolidation_queue || 0)
              ),
              React.createElement(Stat, null,
                React.createElement(StatLabel, null, 'Interactions'),
                React.createElement(StatNumber, null, systemStatus?.interaction_count || 0)
              )
            )
          ),
          React.createElement(TabPanel, null,
            React.createElement(Box, { bg: 'gray.800', borderRadius: 'md', maxH: '400px', overflowY: 'auto', p: 4, fontFamily: 'Fira Code, monospace', fontSize: 'xs' },
              logs.map((log, i) => React.createElement('div', {
                key: i,
                style: {
                  color: log.level === 'error' ? '#fc8181' : log.level === 'warn' ? '#f6ad55' : '#68d391',
                  marginBottom: '2px',
                  whiteSpace: 'pre-wrap'
                }
              }, `[${new Date(log.timestamp).toLocaleTimeString()}] ${log.text}`))
            )
          )
        )
      )
    )
  );
}

const container = document.getElementById('root');
const root = ReactDOM.createRoot(container);
root.render(React.createElement(CALIDashboard));
