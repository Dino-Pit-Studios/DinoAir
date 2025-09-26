import React, { useMemo, useState } from 'react';

import Button from '../components/common/Button';
import Card from '../components/common/Card';
import SearchInput from '../components/common/SearchInput';
import ArtifactsIcon from '../components/icons/ArtifactsPage';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';

type Artifact = {
  id: number;
  name: string;
  type: string;
  size: string;
};

/**
 * ArtifactsPage component renders a searchable list of artifacts with actions.
 *
 * @returns {JSX.Element} The rendered Artifacts page component.
 */
export default function ArtifactsPage() {
  const [q, setQ] = useState('');
  const [artifacts] = useState<Artifact[]>([
    { id: 1, name: 'model-v1.onnx', type: 'Model', size: '24.3 MB' },
    { id: 2, name: 'report-sprint1.pdf', type: 'Report', size: '1.2 MB' },
    { id: 3, name: 'vector.index', type: 'Index', size: '56.7 MB' },
    { id: 4, name: 'dataset.csv', type: 'Data', size: '4.8 MB' },
  ]);

  const filtered = useMemo(
    () =>
      artifacts.filter(
        a =>
          a.name.toLowerCase().includes(q.toLowerCase()) ||
          a.type.toLowerCase().includes(q.toLowerCase())
      ),
    [artifacts, q]
  );

  const handleViewClick = React.useCallback((_e: React.MouseEvent<HTMLButtonElement>) => {
    /* placeholder */
  }, []);

  const handleDownloadClick = React.useCallback((_e: React.MouseEvent<HTMLButtonElement>) => {
    /* download noop */
  }, []);

  return (
    <PageContainer className='artifacts-page'>
      <PageHeader icon={<ArtifactsIcon width={20} height={20} />} title='Artifacts' />

      <section
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <div style={{ flex: 1 }}>
          <SearchInput value={q} onChange={setQ} placeholder='Search artifacts...' />
        </div>
      </section>

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 12,
        }}
      >
        {filtered.map(a => (
          <Card
            key={a.id}
            title={a.name}
            footer={
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <Button variant='secondary' data-id={a.id} onClick={handleViewClick}>
                  View
                </Button>
                <Button variant='ghost' data-id={a.id} onClick={handleDownloadClick}>
                  Download
                </Button>
              </div>
            }
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 13,
                color: '#cdd6ff',
              }}
            >
              <span>Type: {a.type}</span>
              <span>Size: {a.size}</span>
            </div>
          </Card>
        ))}
      </section>
    </PageContainer>
  );
}
