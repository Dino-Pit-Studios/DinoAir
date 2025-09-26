import { RouterProvider, createHashRouter } from 'react-router-dom';

import { AnnouncementProvider } from './contexts/AnnouncementContext';
import PageShell from './layout/PageShell';
import ArtifactsPage from './pages/ArtifactsPage';
import ChatPage from './pages/ChatPage';
import FilesPage from './pages/FilesPage';
import HomePage from './pages/HomePage';
import ModelSettingsPage from './pages/ModelSettingsPage';
import NotesPage from './pages/NotesPage';
import NotFoundPage from './pages/NotFoundPage';
import ProjectsPage from './pages/ProjectsPage';
import SettingsPage from './pages/SettingsPage';
import ToolsPage from './pages/ToolsPage';
import UtilitiesPage from './pages/UtilitiesPage';

const router = createHashRouter([
  {
    path: '/',
    element: <PageShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'artifacts', element: <ArtifactsPage /> },
      { path: 'notes', element: <NotesPage /> },
      { path: 'tools', element: <ToolsPage /> },
      { path: 'utilities', element: <UtilitiesPage /> },
      { path: 'files', element: <FilesPage /> },
      { path: 'model-settings', element: <ModelSettingsPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

/**
 * App component serves as the root component of the application.
 * It wraps the RouterProvider with AnnouncementProvider to enable announcements and routing.
 * @returns {JSX.Element} The rendered App component.
 */
export default function App() {
  return (
    <AnnouncementProvider>
      <RouterProvider router={router} />
    </AnnouncementProvider>
  );
}
