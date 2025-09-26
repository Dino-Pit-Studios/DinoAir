// no React default import needed with react-jsx

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import Banner from '../components/common/Banner';
import Button from '../components/common/Button';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';

/**
 * NotFoundPage component displays a 404 error page with navigation back to home.
 *
 * @returns {JSX.Element} The NotFoundPage component.
 */
export default function NotFoundPage() {
  const navigate = useNavigate();

  const handleGoHome = useCallback(() => {
    navigate('/');
  }, [navigate]);

  return (
    <PageContainer className='not-found-page'>
      <PageHeader title='Not Found' />

      <Banner type='error'>Page not found</Banner>

      <div style={{ marginTop: 10 }}>
        <Button variant='primary' onClick={handleGoHome}>
          Go to Home
        </Button>
      </div>
    </PageContainer>
  );
}
