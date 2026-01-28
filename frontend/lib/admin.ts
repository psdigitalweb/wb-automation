/**
 * Admin utilities for superuser checks
 */

import { getUser, User } from './auth'

/**
 * Check if current user is superuser
 */
export function isSuperuser(): boolean {
  const user = getUser()
  return user?.is_superuser === true
}

/**
 * Get current user or null
 */
export function getCurrentUser(): User | null {
  return getUser()
}
