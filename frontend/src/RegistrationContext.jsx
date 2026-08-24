import React from 'react';

const safeDefault = {
  mode: 'closed',
  action: 'closed',
  registration_enabled: false,
  waitlist_enabled: false,
  password_required: false,
  setup_code_required: false,
};

export const RegistrationContext = React.createContext({
  ...safeDefault,
  loading: true,
  error: '',
  refresh: () => {},
});

export function RegistrationProvider({ children }) {
  const [status, setStatus] = React.useState(safeDefault);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/registration');
      if (!response.ok) {
        throw new Error(`Registration status returned ${response.status}`);
      }
      const body = await response.json();
      if (!['waitlist', 'create-owner', 'closed'].includes(body.action)) {
        throw new Error('Registration status was invalid');
      }
      setStatus(body);
    } catch (requestError) {
      console.error('Registration status error:', requestError);
      setStatus(safeDefault);
      setError('Registration status is temporarily unavailable.');
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const value = React.useMemo(() => ({
    ...status,
    loading,
    error,
    refresh,
  }), [status, loading, error, refresh]);

  return (
    <RegistrationContext.Provider value={value}>
      {children}
    </RegistrationContext.Provider>
  );
}

export function useRegistration() {
  return React.useContext(RegistrationContext);
}
