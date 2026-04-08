import { createContext, useContext, useState } from 'react';

const RouterContext = createContext(null);

const ROUTES = {
  HOME: 'home',
  LOGIN: 'login',
  SIGNUP: 'signup',
  BILLING: 'billing',
  WORKSPACE: 'workspace',
};

export { ROUTES };

export function RouterProvider({ children }) {
  const [route, setRoute] = useState(ROUTES.HOME);
  const [routeParams, setRouteParams] = useState({});

  function navigate(nextRoute, params = {}) {
    setRoute(nextRoute);
    setRouteParams(params);
    window.scrollTo(0, 0);
  }

  return (
    <RouterContext.Provider value={{ route, routeParams, navigate }}>
      {children}
    </RouterContext.Provider>
  );
}

export function useRouter() {
  const context = useContext(RouterContext);
  if (!context) {
    throw new Error('useRouter must be used within RouterProvider');
  }
  return context;
}
