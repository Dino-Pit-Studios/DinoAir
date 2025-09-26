import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { LiveRegion } from '../components/accessibility/LiveRegion';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import SearchInput from '../components/common/SearchInput';
import Projects from '../components/icons/Projects';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { useAnnouncement } from '../hooks/useAnnouncement';
import { useResponsive } from '../hooks/useResponsive';

type Project = {
  id: number;
  name: string;
  summary: string;
};

/**
 * ProjectsPage component displays a list of projects with search and create functionality.
 * @returns {JSX.Element} The rendered ProjectsPage component.
 */
export default function ProjectsPage() {
  const { isMobile, isBelow } = useResponsive();
  const navigate = useNavigate();
  const { announceSuccess, announceInfo } = useAnnouncement();
  const [q, setQ] = useState('');
  const [projectName, setProjectName] = useState('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [projects, setProjects] = useState<Project[]>([
    {
      id: 1,
      name: 'Apollo',
      summary: 'LLM powered assistant for internal docs',
    },
    {
      id: 2,
      name: 'Nebula',
      summary: 'Artifacts explorer and pipeline runner',
    },
    { id: 3, name: 'Orion', summary: 'Notes and knowledge base' },
    { id: 4, name: 'Pegasus', summary: 'File indexing and semantic search' },
  ]);

  const filtered = useMemo(
    () =>
      projects.filter(
        p =>
          p.name.toLowerCase().includes(q.toLowerCase()) ||
          p.summary.toLowerCase().includes(q.toLowerCase())
      ),
    [projects, q]
  );

  /**
   * Creates a new project if the dialog is open and a name is provided, otherwise opens the create project dialog.
   * @returns {void}
   */
  function createProject() {
    if (showCreateDialog && projectName.trim()) {
      const id = projects.length + 1;
      const newProjectName = projectName.trim();
      setProjects(prev => [
        ...prev,
        { id, name: newProjectName, summary: 'Describe your project...' },
      ]);
      setProjectName('');
      setShowCreateDialog(false);
      announceSuccess(`Created new project: ${newProjectName}`);
    } else {
      setShowCreateDialog(true);
      announceInfo('Create project dialog opened');
    }
  }

  const handleCancelCreate = React.useCallback(() => {
    setShowCreateDialog(false);
    setProjectName('');
    announceInfo('Create project dialog closed');
  }, [announceInfo]);

  const handleOpenCreate = React.useCallback(() => {
    setShowCreateDialog(true);
    announceInfo('Create project dialog opened');
  }, [announceInfo]);

  const handleArtifactsClick = React.useCallback(
    (projectName: string) => () => {
      announceInfo(`Navigating to artifacts for ${projectName}`);
      navigate('/artifacts');
    },
    [announceInfo, navigate]
  );

  const handleNotesClick = React.useCallback(
    (projectName: string) => () => {
      announceInfo(`Navigating to notes for ${projectName}`);
      navigate('/notes');
    },
    [announceInfo, navigate]
  );

  return (
    <PageContainer className='projects-page'>
      <PageHeader icon={<Projects width={20} height={20} />} title='Projects' />

      <main role='main' aria-label='Project management'>
        {/* Create Project Dialog */}
        {showCreateDialog && (
          <div
            role='dialog'
            aria-labelledby='create-project-title'
            aria-modal='true'
            style={{
              background: '#0f3460',
              border: '1px solid #2a3b7a',
              borderRadius: 8,
              padding: 16,
              marginBottom: 16,
            }}
          >
            <h3 id='create-project-title' style={{ margin: '0 0 12px 0', color: '#cdd6ff' }}>
              Create New Project
            </h3>
            <div
              style={{
                display: 'flex',
                gap: 8,
                flexDirection: isMobile ? 'column' : 'row',
              }}
            >
              <SearchInput
                value={projectName}
                onChange={setProjectName}
                placeholder='Enter project name...'
                data-testid='project-name-input'
                aria-label='Project name'
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  onClick={createProject}
                  variant='primary'
                  data-testid='confirm-create-button'
                  disabled={!projectName.trim()}
                  style={{ minWidth: isMobile ? '100%' : 'auto' }}
                >
                  Create
                </Button>
                <Button
                  onClick={handleCancelCreate}
                  variant='secondary'
                  data-testid='cancel-create-button'
                  style={{ minWidth: isMobile ? '100%' : 'auto' }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        )}

        <section
          style={{
            display: 'flex',
            flexDirection: isMobile ? 'column' : 'row',
            gap: 8,
            alignItems: isMobile ? 'stretch' : 'center',
            marginBottom: 12,
          }}
          role='search'
          aria-label='Project search'
        >
          <div style={{ flex: 1 }}>
            <SearchInput
              value={q}
              onChange={setQ}
              placeholder='Search projects...'
              data-testid='project-search-input'
              aria-label='Search projects'
            />
          </div>
          <Button
            onClick={handleOpenCreate}
            variant='primary'
            data-testid='new-project-button'
            aria-label='Create new project'
            style={{
              minWidth: isMobile ? '100%' : 'auto',
            }}
          >
            Create New Project
          </Button>
        </section>

        <section
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile
              ? '1fr'
              : isBelow('tablet')
                ? 'repeat(auto-fill, minmax(280px, 1fr))'
                : 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 12,
          }}
          role='list'
          aria-label='Projects list'
        >
          {filtered.map(p => (
            <article key={p.id} role='listitem' aria-label={`Project: ${p.name}`}>
              <Card
                title={p.name}
                data-testid={`project-card-${p.id}`}
                footer={
                  <div
                    style={{
                      display: 'flex',
                      gap: 8,
                      justifyContent: 'flex-end',
                      flexWrap: 'wrap',
                    }}
                  >
                    <Button
                      variant='ghost'
                      onClick={handleArtifactsClick(p.name)}
                      aria-label={`View artifacts for ${p.name}`}
                      style={{ minWidth: isMobile ? '45%' : 'auto' }}
                    >
                      Artifacts
                    </Button>
                    <Button
                      variant='secondary'
                      onClick={handleNotesClick(p.name)}
                      aria-label={`View notes for ${p.name}`}
                      style={{ minWidth: isMobile ? '45%' : 'auto' }}
                    >
                      Notes
                    </Button>
                  </div>
                }
              >
                <p style={{ margin: 0, color: '#cdd6ff', fontSize: 14 }}>{p.summary}</p>
              </Card>
            </article>
          ))}

          {filtered.length === 0 && (
            <div
              role='status'
              aria-live='polite'
              style={{
                gridColumn: '1 / -1',
                textAlign: 'center',
                color: '#9fb3ff',
                padding: '40px 20px',
              }}
            >
              {q ? `No projects found matching "${q}"` : 'No projects available'}
            </div>
          )}
        </section>
      </main>

      {/* Screen reader live region for announcements */}
      <LiveRegion ariaLabel='Projects page announcements' showLatestOnly />
    </PageContainer>
  );
}
