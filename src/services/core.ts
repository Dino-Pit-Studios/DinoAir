/**
 * Core service integration for Tools page.
 * Includes read-only GET calls and selected mutation calls.
 */
import { request } from '../lib/api';

export type CurrentTimeResponse = { iso?: string } & Record<string, unknown>;
export type ListDirectoryResponse = {
  entries?: string[];
  [key: string]: unknown;
};
export type AddTwoNumbersResponse = {
  result?: number;
  [key: string]: unknown;
};

/**
 * Retrieves the current time from the core service.
 * @returns A promise that resolves with the current time response.
 */
export function getCurrentTime(): Promise<CurrentTimeResponse> {
  return request('/core/current-time');
}

/**
 * Retrieves a list of directory entries at the specified path.
 *
 * @param path - The directory path to list.
 * @returns A Promise that resolves to a ListDirectoryResponse object containing the directory entries.
 */
export function listDirectory(path: string): Promise<ListDirectoryResponse> {
  const qp = `?path=${encodeURIComponent(path)}`;
  return request(`/core/list-directory${qp}`);
}

/**
 * Sends a POST request to the core service to add two numbers.
 * @param {number} a - The first number to add.
 * @param {number} b - The second number to add.
 * @returns {Promise<AddTwoNumbersResponse>} A promise that resolves with the response containing the sum of the two numbers.
 */
export function addTwoNumbers(a: number, b: number): Promise<AddTwoNumbersResponse> {
  return request('/core/add-two-numbers', {
    method: 'POST',
    body: JSON.stringify({ a, b }),
  });
}
