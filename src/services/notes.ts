/**
 * Notes service integration - read-only GET calls and create mutation.
 */
import { request } from '../lib/api';

export type Note = {
  id: string | number;
  title?: string;
  content?: string;
  tags?: string[];
  createdAt?: string;
  updatedAt?: string;
} & Record<string, unknown>;

export type TagsResponse = { tags: string[] };
export type NotesByTagResponse = {
  notes: Note[];
  count?: number;
  tag?: string;
  success?: boolean;
  message?: string;
};

/**
 * Retrieves all notes from the server.
 *
 * @returns {Promise<Note[]>} A promise that resolves with an array of Note objects.
 */
export function listAllNotes(): Promise<Note[]> {
  return request('/notes');
}

/**
 * Searches notes matching the given query string.
 * @param q - The search query string.
 * @returns A promise that resolves to an array of Note objects.
 */
export function searchNotes(q: string): Promise<Note[]> {
  const qp = `?q=${encodeURIComponent(q)}`;
  return request(`/notes/search${qp}`);
}

/**
 * Retrieves all tags associated with notes.
 *
 * @returns {Promise<TagsResponse>} A promise that resolves to the tags response.
 */
/**
 * Retrieves all note tags.
 * @returns {Promise<TagsResponse>} A promise that resolves to the tags response.
 */
export function getAllTags(): Promise<TagsResponse> {
  return request('/notes/tags');
}

/**
 * Retrieves notes matching the provided tag name.
 * @param tag - Tag value to filter notes by.
 * @returns A promise that resolves with the notes (or envelope) returned by the API.
 */
export function getNotesByTag(tag: string): Promise<NotesByTagResponse> {
  const qp = `?tag=${encodeURIComponent(tag)}`;
  return request(`/notes/by-tag${qp}`);
}

/**
 * Creates a new note with the provided title, content, and optional tags.
 * @param input - The note data including title, content, and optional tags.
 * @returns A Promise that resolves to the created Note object.
 */
export function createNote(input: {
  title: string;
  content: string;
  tags?: string[];
}): Promise<Note> {
  return request('/notes', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}
