/**
 * Projects service integration - read-only GET calls for connectivity tests.
 */
import { request } from '../lib/api';

export type Project = Record<string, unknown>;
export type Projects = Project[];
export interface ProjectStats {
  totalProjects: number;
  activeProjects: number;
  archivedProjects: number;
  [key: string]: number; // If there may be additional numeric stats
}

/**
 * Retrieves all projects.
 *
 * @returns Promise<Projects> A promise that resolves to the list of projects.
 */
export function listAll(): Promise<Projects> {
  return request('/projects');
}

/**
 * Retrieves a project by its unique identifier.
 *
 * @param id - The unique identifier of the project, as a string or number.
 * @returns A promise that resolves to the retrieved Project.
 */
export function get(id: string | number): Promise<Project> {
  return request(`/projects/${encodeURIComponent(String(id))}`);
}

/**
 * Searches for projects matching the specified query.
 *
 * @param {string} q - The search query string.
 * @returns {Promise<Projects>} A promise that resolves to the matching projects.
 */
export function search(q: string): Promise<Projects> {
  const qp = `?q=${encodeURIComponent(q)}`;
  return request(`/projects/search${qp}`);
}

/**
 * Fetches projects with the specified status.
 *
 * @param status - The project status to filter by.
 * @returns A promise that resolves to the projects matching the status.
 */
export function byStatus(status: string): Promise<Projects> {
  const qp = `?status=${encodeURIComponent(status)}`;
  return request(`/projects/by-status${qp}`);
}

/**
 * Retrieves statistics for all projects.
 *
 * @returns {Promise<ProjectStats>} A promise that resolves to project statistics.
 */
export function getStats(): Promise<ProjectStats> {
  return request('/projects/stats');
}

/**
 * Retrieves the file tree for a specific project.
 * @param id - The project ID as a string or number.
 * @returns A promise resolving to a record containing the project's tree structure.
 */
export function getTree(id: string | number): Promise<Record<string, unknown>> {
  return request(`/projects/${encodeURIComponent(String(id))}/tree`);
}
