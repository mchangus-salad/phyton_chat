import { useCallback, useState } from 'react';
import { apiPost } from '../../../shared/api/http';

const emptyForm = {
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
  firstName: '',
  lastName: '',
};

export function useSignup({ onSuccess }) {
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});

  function setField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  const submit = useCallback(async () => {
    setError('');
    setFieldErrors({});

    const errors = {};
    if (!form.username.trim()) errors.username = 'Username is required.';
    if (!form.email.trim()) errors.email = 'Email is required.';
    if (!form.password) errors.password = 'Password is required.';
    if (form.password && form.password.length < 8) errors.password = 'Password must be at least 8 characters.';
    if (form.password !== form.confirmPassword) errors.confirmPassword = 'Passwords do not match.';

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return null;
    }

    setLoading(true);
    try {
      const response = await apiPost('/auth/register/', {
        username: form.username.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
      });
      if (onSuccess) onSuccess(response);
      return response;
    } catch (apiError) {
      const detail = apiError?.payload?.detail;
      if (typeof detail === 'string') {
        setError(detail);
      } else if (Array.isArray(detail)) {
        setError(detail.join(' '));
      } else {
        setError(apiError?.payload?.error || 'Registration failed. Please try again.');
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [form, onSuccess]);

  return { form, setField, loading, error, fieldErrors, submit };
}
