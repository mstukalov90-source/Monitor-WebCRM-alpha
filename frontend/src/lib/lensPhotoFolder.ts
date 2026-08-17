const DB_NAME = 'webcrm-lens-photos'
const DB_VERSION = 1
const STORE = 'handles'
const HANDLE_KEY = 'root'

type FsPermission = 'granted' | 'denied' | 'prompt'

interface FsFileHandle {
  getFile(): Promise<File>
}

export interface LensPhotoFolderHandle {
  getDirectoryHandle(name: string): Promise<LensPhotoFolderHandle>
  getFileHandle(name: string): Promise<FsFileHandle>
  queryPermission?: (descriptor?: { mode?: 'read' }) => Promise<FsPermission>
  requestPermission?: (descriptor?: { mode?: 'read' }) => Promise<FsPermission>
}

function showDirectoryPicker():
  | ((options?: { id?: string; mode?: 'read' }) => Promise<LensPhotoFolderHandle>)
  | undefined {
  const picker = (window as Window & {
    showDirectoryPicker?: (options?: { id?: string; mode?: 'read' }) => Promise<LensPhotoFolderHandle>
  }).showDirectoryPicker
  return typeof picker === 'function' ? picker.bind(window) : undefined
}

export function isLensPhotoFolderApiSupported(): boolean {
  return showDirectoryPicker() != null
}

export function windowsPathToFileUrl(windowsPath: string): string {
  const normalized = windowsPath.trim().replace(/\\/g, '/')
  const withRoot = normalized.replace(/^([A-Za-z]:)/, '/$1')
  const encoded = withRoot
    .split('/')
    .map((part, index) => {
      if (index === 1 && /^[A-Za-z]:$/.test(part)) return part
      return encodeURIComponent(part)
    })
    .join('/')
  return `file://${encoded}`
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
  })
}

async function saveFolderHandle(handle: LensPhotoFolderHandle): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB write failed'))
    tx.objectStore(STORE).put(handle, HANDLE_KEY)
  })
  db.close()
}

async function loadFolderHandle(): Promise<LensPhotoFolderHandle | null> {
  const db = await openDb()
  const handle = await new Promise<LensPhotoFolderHandle | null>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).get(HANDLE_KEY)
    req.onsuccess = () => resolve((req.result as LensPhotoFolderHandle | undefined) ?? null)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB read failed'))
  })
  db.close()
  return handle
}

async function ensureReadPermission(handle: LensPhotoFolderHandle): Promise<boolean> {
  try {
    const query = handle.queryPermission
    if (query) {
      const state = await query({ mode: 'read' })
      if (state === 'granted') return true
      if (state === 'denied') return false
    }
    const request = handle.requestPermission
    if (request) {
      return (await request({ mode: 'read' })) === 'granted'
    }
    return true
  } catch {
    return false
  }
}

export async function pickLensPhotoFolder(): Promise<LensPhotoFolderHandle> {
  const picker = showDirectoryPicker()
  if (!picker) {
    throw new Error('Выбор папки не поддерживается в этом браузере')
  }
  const handle = await picker({ id: 'lens-obektiv', mode: 'read' })
  await saveFolderHandle(handle)
  return handle
}

export async function getStoredLensPhotoFolder(): Promise<LensPhotoFolderHandle | null> {
  try {
    const handle = await loadFolderHandle()
    if (!handle) return null
    if (await ensureReadPermission(handle)) return handle
    return null
  } catch {
    return null
  }
}

export async function resolveFileFromLensFolder(
  root: LensPhotoFolderHandle,
  relativePath: string,
): Promise<File | null> {
  const segments = relativePath.split('/').filter(Boolean)
  if (!segments.length || segments.some((part) => part === '..' || part === '.')) {
    return null
  }
  try {
    let dir = root
    for (let i = 0; i < segments.length - 1; i += 1) {
      dir = await dir.getDirectoryHandle(segments[i])
    }
    const fileHandle = await dir.getFileHandle(segments[segments.length - 1])
    return await fileHandle.getFile()
  } catch {
    return null
  }
}
