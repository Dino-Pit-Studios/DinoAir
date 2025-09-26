import { useCallback, useMemo, useState, type CSSProperties, type ReactNode } from 'react';

import { LiveRegion } from '../components/accessibility/LiveRegion';
import Banner from '../components/common/Banner';
import Button from '../components/common/Button';
import FooterLinks from '../components/common/FooterLinks';
import SearchInput from '../components/common/SearchInput';
import Table from '../components/common/Table';
import LocalFileRetrievalAndIndexing from '../components/icons/LocalFileRetrievalAndIndexing';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { useAnnouncement } from '../hooks/useAnnouncement';
import { useResponsive } from '../hooks/useResponsive';
import { ragApi, type RagEnvelope } from '../lib/api';

type FileRow = {
  id: number;
  name: string;
  category: string;
  size: string;
  indexed: boolean;
};

/**
 * Cosmetic deterministic size generator to avoid PRNG usage (typescript:S2245).
 * Maps the file name and id to a stable float in [0,1) via a simple 32-bit hash,
 * then scales it to roughly 0.2–2.2 MB. Purely for display.
 */
function deterministicSizeMBLabel(name: string, id: number): string {
  const input = `${name}#${id}`;
  // FNV-1a 32-bit hash
  let h = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  const mapped = (h >>> 0) / 0x100000000; // [0,1)
  const sizeMB = mapped * 2 + 0.2; // ~0.2–2.2 MB
  return `${sizeMB.toFixed(1)} MB`;
}

/**
 * FilesPage component renders the file management interface including category tabs, search input, file table, and related actions.
 * @returns JSX.Element The rendered files page component.
 */
export default function FilesPage() {
  const { isMobile } = useResponsive();
  const { announceSuccess, announceError, announceInfo, announceWarning } = useAnnouncement();
  const [categories] = useState<string[]>(['Documents', 'Datasets', 'Models', 'Indexes']);
  const [activeCat, setActiveCat] = useState<string>('Documents');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [files, setFiles] = useState<FileRow[]>([
    {
      id: 1,
      name: 'requirements.docx',
      category: 'Documents',
      size: '88 KB',
      indexed: true,
    },
    {
      id: 2,
      name: 'dataset.csv',
      category: 'Datasets',
      size: '4.8 MB',
      indexed: false,
    },
    {
      id: 3,
      name: 'model-v1.onnx',
      category: 'Models',
      size: '24.3 MB',
      indexed: false,
    },
    {
      id: 4,
      name: 'vector.index',
      category: 'Indexes',
      size: '56.7 MB',
      indexed: true,
    },
  ]);
  const [banner, setBanner] = useState<{
    type: 'info' | 'success' | 'error' | 'warning';
    text: string;
  } | null>(null);

  const categoryHandlers = useMemo(() => {
    const handlers: Record<string, () => void> = {};
    categories.forEach(category => {
      handlers[category] = () => {
        setActiveCat(category);
        announceInfo(`Showing ${category} files`);
      };
    });
    return handlers;
  }, [categories, announceInfo, setActiveCat]);

  const handleSearchInputChange = useCallback(
    (value: string) => {
      setSearchQuery(value);
    },
    [setSearchQuery]
  );

  const handleGenerateMissingEmbeddings = useCallback(() => {
    const message = 'Requested generation of missing embeddings.';
    setBanner({ type: 'info', text: message });
    announceInfo(message);
  }, [announceInfo, setBanner]);

  /**
   * Adds a new file to the current category with a deterministic size and announces success.
   * @returns void
   */
  function addNewFile() {
    const id = files.length ? Math.max(...files.map(f => f.id)) + 1 : 1;
    const fileName = `new-file-${id}.txt`;
    setFiles(prev => [
      ...prev,
      {
        id,
        name: fileName,
        category: activeCat,
        size: deterministicSizeMBLabel(fileName, id),
        indexed: false,
      },
    ]);
    announceSuccess(`Added new file: ${fileName} to ${activeCat}`);
  }

  /**
   * Index a file by its id, triggering ingestion and updating UI state.
   * @param id - The unique identifier of the file to index.
   * @returns A promise that resolves when the indexing process is complete.
   */
  async function indexFile(id: number) {
    setBanner(null);
    const row = files.find(f => f.id === id);
    if (!row) {
      return;
    }
    try {
      const path =
        /^(?:[a-zA-Z]:\\|\\\\|\/)/.test(row.name) ||
        row.name.includes('/') ||
        row.name.includes('\\')
          ? row.name
          : window.prompt('Enter full file path for ingestion:', row.name) || row.name;

      const res = (await ragApi.ingestFiles({
        paths: [path],
      })) as RagEnvelope;
      if (res && typeof res === 'object' && 'success' in res) {
        if (res.success) {
          setFiles(prev => prev.map(f => (f.id === id ? { ...f, indexed: true } : f)));
          const counts = 'data' in res ? (res.data as unknown) : undefined;
          const parts: string[] = [];
          if (counts && typeof counts === 'object') {
            const cf = counts as { processed_files?: number; processed_chunks?: number };
            if (typeof cf.processed_files === 'number') parts.push(`files: ${cf.processed_files}`);
            if (typeof cf.processed_chunks === 'number')
              parts.push(`chunks: ${cf.processed_chunks}`);
          }
          const successMsg = `Ingestion complete${parts.length ? ` (${parts.join(', ')})` : ''}.`;
          setBanner({
            type: 'success',
            text: successMsg,
          });
          announceSuccess(successMsg);
        } else if ('code' in res && (res as { code?: number }).code === 501) {
          const warningMsg =
            'RAG unavailable. Use Tools > RAG operations to ingest files and generate embeddings.';
          setBanner({
            type: 'warning',
            text: warningMsg,
          });
          announceWarning(warningMsg);
        } else {
          const errorMsg =
            'error' in res && typeof res.error === 'string' ? res.error : 'Ingestion failed.';
          setBanner({
            type: 'error',
            text: errorMsg,
          });
          announceError(errorMsg);
        }
      } else {
        // Non-envelope response; do not assume indexing success
        setBanner({
          type: 'info',
          text: 'Ingestion requested. Awaiting processing…',
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setBanner({ type: 'error', text: msg });
    }
  }

  const filtered = useMemo(() => {
    let result = files.filter(f => f.category === activeCat);

    // Apply search filter if query exists
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        f => f.name.toLowerCase().includes(query) || f.category.toLowerCase().includes(query)
      );
    }

    return result;
  }, [files, activeCat, searchQuery]);

  const columns = ['Name', 'Category', 'Size', 'Status', 'Actions'];

  const indexHandlers = useMemo(() => {
    const handlers: Record<string, () => void> = {};
    filtered.forEach(f => {
      handlers[f.id] = () => {
        indexFile(f.id);
        return undefined;
      };
    });
    return handlers;
  }, [filtered, indexFile]);

  const rows = filtered.map(f => {
    const dotStyle: CSSProperties = {
      display: 'inline-block',
      width: 8,
      height: 8,
      borderRadius: 4,
      background: f.indexed ? '#32bc9b' : '#7a2a2f',
      marginRight: 6,
    };
    return [
      f.name,
      f.category,
      f.size,
      <span key={`s-${f.id}`} style={{ color: f.indexed ? '#aef2de' : '#ffd1d1' }}>
        <span style={dotStyle} /> {f.indexed ? 'Indexed' : 'Not Indexed'}
      </span>,
      <Button
        key={`b-${f.id}`}
        variant='secondary'
        onClick={indexHandlers[f.id]}
        disabled={f.indexed}
      >
        Index
      </Button>,
    ] as (string | number | ReactNode)[];
  });

  return (
    <PageContainer className='files-page'>
      <PageHeader icon={<LocalFileRetrievalAndIndexing width={20} height={20} />} title='Files' />

      <main role='main' aria-label='File management'>
        <section
          style={{
            display: isMobile ? 'flex' : 'grid',
            flexDirection: isMobile ? 'column' : undefined,
            gridTemplateColumns: isMobile ? undefined : '220px 1fr',
            gap: 16,
          }}
        >
          <aside
            style={{
              marginBottom: isMobile ? 16 : 0,
            }}
          >
            <h3 style={{ marginTop: 0, fontSize: 14, color: '#cdd6ff' }}>Categories</h3>
            <nav aria-label='File categories'>
              <div
                style={{
                  display: isMobile ? 'flex' : 'grid',
                  flexWrap: isMobile ? 'wrap' : undefined,
                  gap: 6,
                }}
                role='tablist'
              >
                {categories.map(c => (
                  <button
                    key={c}
                    onClick={categoryHandlers[c]}
                    className='nav-link'
                    role='tab'
                    aria-selected={activeCat === c}
                    aria-controls={`${c.toLowerCase()}-panel`}
                    data-testid={`category-${c.toLowerCase()}`}
                    style={{
                      width: isMobile ? 'auto' : '100%',
                      textAlign: 'left',
                      background: activeCat === c ? '#23346e' : '#0f3460',
                      border: '1px solid #2a3b7a',
                      color: '#e6eaff',
                      padding: '8px 10px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontWeight: activeCat === c ? 700 : 500,
                      minWidth: isMobile ? '100px' : undefined,
                    }}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </nav>
          </aside>

          <div
            style={{ display: 'grid', gap: 10 }}
            role='tabpanel'
            id={`${activeCat.toLowerCase()}-panel`}
            aria-labelledby={`category-${activeCat.toLowerCase()}`}
          >
            <div
              style={{
                display: 'flex',
                flexDirection: isMobile ? 'column' : 'row',
                justifyContent: 'space-between',
                alignItems: isMobile ? 'stretch' : 'center',
                gap: isMobile ? 8 : 0,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 16, color: '#cdd6ff' }}>{activeCat}</h3>

              {/* Search Section for Files */}
              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  marginBottom: isMobile ? 8 : 0,
                }}
              >
                <div style={{ flex: 1, minWidth: '200px' }}>
                  <SearchInput
                    value={searchQuery}
                    onChange={handleSearchInputChange}
                    placeholder='Search files...'
                    data-testid='file-search-input'
                    aria-label='Search files'
                  />
                </div>
                <Button variant='secondary' data-testid='search-button' aria-label='Search files'>
                  Search
                </Button>
              </div>

              <div
                style={{
                  display: 'flex',
                  flexDirection: isMobile ? 'column' : 'row',
                  gap: 8,
                }}
              >
                <Button
                  variant='secondary'
                  data-testid='generate-embeddings-button'
                  aria-label='Generate missing embeddings'
                  onClick={handleGenerateMissingEmbeddings}
                  style={{
                    width: isMobile ? '100%' : 'auto',
                  }}
                >
                  Generate Missing Embeddings
                </Button>
                <Button
                  variant='primary'
                  onClick={addNewFile}
                  data-testid='add-file-button'
                  aria-label='Add new file'
                  style={{
                    width: isMobile ? '100%' : 'auto',
                  }}
                >
                  Add New File
                </Button>
              </div>
            </div>
            {banner && (
              <div role='alert' aria-live='polite'>
                <Banner type={banner.type}>{banner.text}</Banner>
              </div>
            )}
            <div
              data-testid='files-table'
              style={{
                overflowX: isMobile ? 'auto' : 'visible',
              }}
            >
              <Table columns={columns} rows={rows} aria-label='Files list' />
            </div>
            <div style={{ marginTop: 8 }}>
              <FooterLinks />
            </div>
          </div>
        </section>
      </main>

      {/* Screen reader live region for announcements */}
      <LiveRegion ariaLabel='Files page announcements' showLatestOnly />
    </PageContainer>
  );
}
