/**
 * File Search service integration - read-only GET calls and index mutations.
 */
import { request } from '../lib/api';

// Define interfaces for API responses
export interface SearchResult {
  files: Array<{
    path: string;
    name: string;
    size: number;
    modified: string; // ISO date string
    [key: string]: unknown; // For any additional fields
  }>;
  total: number;
  [key: string]: unknown;
}

export interface FileInfo {
  path: string;
  name: string;
  size: number;
  modified: string; // ISO date string
  type: string;
  [key: string]: unknown;
}

export interface SearchStats {
  totalFiles: number;
  totalDirectories: number;
  lastIndexed: string; // ISO date string
  [key: string]: unknown;
}

export interface Directories {
  directories: string[];
  [key: string]: unknown;
}

export interface FileEmbeddings {
  path: string;
  embeddings: number[];
  [key: string]: unknown;
}
/**
 * Searches for files matching the provided keywords.
 *
 * @param keywords - The keywords to search for.
 * @returns A promise that resolves with the search results.
 */
export function searchByKeywords(keywords: string): Promise<SearchResult> {
  const qp = `?keywords=${encodeURIComponent(keywords)}`;
  return request(`/files/search${qp}`);
}

/**
 * Retrieves information about a file at the specified path.
 * @param path - The path of the file to retrieve information for.
 * @returns A promise that resolves to a FileInfo object containing the file details.
 */
export function getFileInfo(path: string): Promise<FileInfo> {
  const qp = `?path=${encodeURIComponent(path)}`;
  return request(`/files/info${qp}`);
}

/**
 * Retrieves search statistics.
 * @returns {Promise<SearchStats>} A promise that resolves to the search statistics.
 */
export function getStats(): Promise<SearchStats> {
  return request('/search/stats');
}

/**
 * Retrieves the available directories from the search service.
 * @returns {Promise<Directories>} A promise resolving to the Directories object.
 */
export function getDirectories(): Promise<Directories> {
  return request('/search/directories');
}

/**
 * Retrieves embeddings for a file at the specified path.
 *
 * @param path - The path to the file.
 * @returns A promise that resolves to the file embeddings.
 */
export function getFileEmbeddings(path: string): Promise<FileEmbeddings> {
  const qp = `?path=${encodeURIComponent(path)}`;
  return request(`/files/embeddings${qp}`);
}

/**
 * Adds a file path to the search index.
 *
 * @param path - The file system path to add to the index.
 * @returns A promise resolving with an object containing an optional success flag and additional data.
 */
export function addFileToIndex(
  path: string
): Promise<{ success?: boolean } & Record<string, unknown>> {
  return request('/files/index', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export function removeFileFromIndex(
  path: string
): Promise<{ success?: boolean } & Record<string, unknown>> {
  // Using body payload for DELETE per README semantics (server should support).
  return request('/files/index', {
    method: 'DELETE',
    body: JSON.stringify({ path }),
  });
}
