import { useMemo, useState } from 'react';

import { LiveRegion } from '../components/accessibility/LiveRegion';
import Banner from '../components/common/Banner';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import SearchInput from '../components/common/SearchInput';
import Notes from '../components/icons/Notes';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { useAnnouncement } from '../hooks/useAnnouncement';
import { useResponsive } from '../hooks/useResponsive';

type Note = { id: number; title: string; content: string };

/**
 * NotesPage component displays and manages a list of notes.
 * @returns JSX.Element The rendered notes page component.
 */
export default function NotesPage() {
  const { isMobile } = useResponsive();
  const { announceSuccess, announceInfo, announceWarning } = useAnnouncement();
  const [q, setQ] = useState('');
  const [notes, setNotes] = useState<Note[]>([
    {
      id: 1,
      title: 'Weekly Team Meeting',
      content: 'Action items and outcomes...',
    },
    {
      id: 2,
      title: 'Sprint 1 Plan',
      content: 'Goals and tasks for sprint 1...',
    },
    {
      id: 3,
      title: 'Retro Ideas',
      content: 'What went well, what can improve...',
    },
  ]);
  const [selectedId, setSelectedId] = useState<number | null>(1);
  const [infoOpen] = useState(true);
  const [successOpen, setSuccessOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const filtered = useMemo(
    () => notes.filter(n => n.title.toLowerCase().includes(q.toLowerCase())),
    [notes, q]
  );

  const selected = notes.find(n => n.id === selectedId) ?? null;

  /**
   * Creates a new note with a unique id and default content.
   * Updates the notes list, selects the new note, and announces success.
   * @returns void
   */
  function createNote() {
    const id = notes.length ? Math.max(...notes.map(n => n.id)) + 1 : 1;
    const newNote: Note = {
      id,
      title: `Untitled ${id}`,
      content: 'Write something...',
    };
    setNotes(n => [newNote, ...n]);
    setSelectedId(id);
    setSuccessOpen(true);
    announceSuccess(`Created new note: ${newNote.title}`);
    setTimeout(() => setSuccessOpen(false), 1000);
  }

  /**
   * Deletes the currently selected note from the list, clears selection, and announces success.
   * @returns void
   */
  function deleteNote() {
    if (!selected) {
      return;
    }
    const deletedTitle = selected.title;
    setNotes(n => n.filter(x => x.id !== selected.id));
    setSelectedId(null);
    setConfirmOpen(false);
    announceSuccess(`Deleted note: ${deletedTitle}`);
  }

  const handleCancelDelete = useCallback(() => {
    setConfirmOpen(false);
  }, []);

  const handleConfirmDelete = useCallback(() => {
    if (selected) {
      setConfirmOpen(true);
      announceWarning(`Delete confirmation required for: ${selected.title}`);
    }
  }, [selected, announceWarning]);

  const noteClickHandlers = useMemo(() => {
    const handlers: Record<string, () => void> = {};
    filtered.forEach(n => {
      handlers[n.id] = () => {
        setSelectedId(n.id);
        announceInfo(`Selected note: ${n.title}`);
      };
    });
    return handlers;
  }, [filtered, announceInfo]);

  return (
    <PageContainer className='notes-page'>
      <PageHeader icon={<Notes width={20} height={20} />} title='Notes' />

      <main role='main' aria-label='Notes management'>
        <section
          style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : '2fr 3fr',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {infoOpen ? (
              <div role='status' aria-live='polite'>
                <Banner type='info'>Use the search bar to find notes quickly.</Banner>
              </div>
            ) : null}
            {successOpen ? (
              <div role='alert' aria-live='polite'>
                <Banner type='success'>Note created.</Banner>
              </div>
            ) : null}
            {confirmOpen ? (
              <div
                role='alertdialog'
                aria-labelledby='delete-confirmation'
                aria-describedby='delete-warning'
              >
                <Banner type='warning'>
                  <span id='delete-confirmation'>Confirm deletion?</span>
                  <span id='delete-warning'> This cannot be undone.</span>
                  <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                    <Button
                      variant='primary'
                      onClick={deleteNote}
                      data-testid='confirm-delete-button'
                      aria-label='Confirm delete'
                    >
                      Confirm
                    </Button>
                    <Button
                      variant='secondary'
                      onClick={handleCancelDelete}
                      data-testid='cancel-delete-button'
                      aria-label='Cancel delete'
                    >
                      Cancel
                    </Button>
                  </div>
                </Banner>
              </div>
            ) : null}

            <SearchInput
              value={q}
              onChange={setQ}
              placeholder='Search notes...'
              data-testid='notes-search-input'
              aria-label='Search notes'
            />

            <Card title='Notes' style={{ minHeight: isMobile ? 200 : 280 }}>
              <nav aria-label='Notes list'>
                <ul
                  style={{
                    listStyle: 'none',
                    padding: 0,
                    margin: 0,
                    display: 'grid',
                    gap: 6,
                  }}
                  role='listbox'
                  aria-label='Available notes'
                >
                  {filtered.map(n => (
                    <li key={n.id} role='option' aria-selected={selectedId === n.id}>
                      <button
                        onClick={noteClickHandlers[n.id]}
                        data-testid={`note-item-${n.id}`}
                        aria-label={`Select note: ${n.title}`}
                        style={{
                          width: '100%',
                          textAlign: 'left',
                          background: selectedId === n.id ? '#23346e' : '#0f3460',
                          border: '1px solid #2a3b7a',
                          color: '#e6eaff',
                          padding: '8px 10px',
                          borderRadius: 8,
                          cursor: 'pointer',
                        }}
                      >
                        {n.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
            </Card>

            <div
              style={{
                display: 'flex',
                gap: 8,
                flexDirection: isMobile ? 'column' : 'row',
              }}
            >
              <Button
                variant='primary'
                onClick={createNote}
                data-testid='create-note-button'
                aria-label='Create new note'
                style={{
                  minWidth: isMobile ? '100%' : 'auto',
                }}
              >
                Create
              </Button>
              <Button
                variant='secondary'
                onClick={handleConfirmDelete}
                disabled={!selected}
                data-testid='delete-note-button'
                aria-label='Delete selected note'
                style={{
                  minWidth: isMobile ? '100%' : 'auto',
                }}
              >
                Delete
              </Button>
            </div>
          </div>

          <aside
            aria-label='Note details'
            style={{
              marginTop: isMobile ? 16 : 0,
            }}
          >
            <Card title='Details'>
              <div data-testid='note-details'>
                {selected ? (
                  <article style={{ display: 'grid', gap: 8 }}>
                    <h2 style={{ fontSize: 16, margin: 0 }}>{selected.title}</h2>
                    <p style={{ margin: 0, color: '#cdd6ff' }}>{selected.content}</p>
                  </article>
                ) : (
                  <span style={{ color: '#9fb3ff' }} role='status'>
                    No note selected.
                  </span>
                )}
              </div>
            </Card>
          </aside>
        </section>
      </main>

      {/* Screen reader live region for announcements */}
      <LiveRegion ariaLabel='Notes page announcements' showLatestOnly />
    </PageContainer>
  );
}
