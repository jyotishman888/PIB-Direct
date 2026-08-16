const STORAGE_KEY = 'pib-direct:prelims-attempts'

interface ArticleAttempts {
  total: number
  answers: Record<number, { selected: number; correct: boolean }>
}

type Store = Record<string, ArticleAttempts>

// Every article card in a list calls getAttemptSummary during render, so the
// parse is cached rather than repeated once per card against a blob that
// grows with every article the reader answers.
let cache: Store | null = null

function readStore(): Store {
  if (cache) return cache
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    cache = raw ? (JSON.parse(raw) as Store) : {}
  } catch {
    cache = {}
  }
  return cache
}

function writeStore(store: Store) {
  cache = store
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    // Storage full or unavailable — attempts just won't persist this session.
  }
}

// Called when a question set renders, so the list view can distinguish
// "never opened" from "opened but not yet answered" once totals are known.
export function recordQuestionTotal(articleId: number, total: number) {
  const store = readStore()
  const key = String(articleId)
  const existing = store[key]
  if (existing?.total === total) return
  store[key] = { total, answers: existing?.answers ?? {} }
  writeStore(store)
}

export function recordAnswer(
  articleId: number,
  questionIndex: number,
  selected: number,
  correct: boolean,
) {
  const store = readStore()
  const key = String(articleId)
  const existing = store[key] ?? { total: 0, answers: {} }
  existing.answers = { ...existing.answers, [questionIndex]: { selected, correct } }
  store[key] = existing
  writeStore(store)
}

export function getAnswer(articleId: number, questionIndex: number) {
  const store = readStore()
  return store[String(articleId)]?.answers[questionIndex] ?? null
}

export interface AttemptSummary {
  total: number
  attempted: number
  correct: number
}

export function getAttemptSummary(articleId: number): AttemptSummary | null {
  const entry = readStore()[String(articleId)]
  if (!entry || entry.total === 0) return null
  const answers = Object.values(entry.answers)
  if (answers.length === 0) return null
  return {
    total: entry.total,
    attempted: answers.length,
    correct: answers.filter((a) => a.correct).length,
  }
}
