'use client'

import { useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import { searchDocs, type DocItem } from '@/lib/docs'

export default function SearchCommand() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<DocItem[]>([])
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Listen for CTRL+K or CMD+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(true)
      }

      // Close on Escape
      if (e.key === 'Escape') {
        setOpen(false)
      }

      // Navigation with arrow keys
      if (open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault()
        setSelectedIndex((prev) => {
          const next =
            e.key === 'ArrowDown'
              ? (prev + 1) % Math.max(results.length, 1)
              : (prev - 1 + Math.max(results.length, 1)) % Math.max(results.length, 1)
          return next
        })
      }

      // Select with Enter
      if (open && e.key === 'Enter' && results.length > 0) {
        e.preventDefault()
        const selected = results[selectedIndex]
        if (selected) {
          window.location.href = selected.path
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, results, selectedIndex])

  // Update results when query changes
  useEffect(() => {
    setResults(searchDocs(query))
    setSelectedIndex(0)
  }, [query])

  // Focus input when dialog opens
  useEffect(() => {
    if (open) {
      inputRef.current?.focus()
    }
  }, [open])

  // Prevent scrolling when modal is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [open])

  return (
    <>
      {/* Search Button in Nav */}
      <button
        onClick={() => setOpen(true)}
        className="search-trigger"
        title="Search docs (Ctrl+K)"
        aria-label="Search documentation"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <span className="search-trigger-kbd">
          <kbd>Ctrl</kbd>
          <kbd>K</kbd>
        </span>
      </button>

      {/* Modal Backdrop */}
      {open && (
        <div
          className="search-backdrop"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Search Dialog */}
      <dialog
        className={`search-dialog${open ? ' is-open' : ''}`}
        open={open}
      >
        <div className="search-dialog-content">
          {/* Search Input */}
          <div className="search-input-wrapper">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="search-icon"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              ref={inputRef}
              type="text"
              placeholder="Search documentation..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="search-input"
              aria-label="Search documentation"
            />
          </div>

          {/* Results */}
          <div className="search-results">
            {query.trim() === '' ? (
              <div className="search-empty">
                <p>Start typing to search documentation...</p>
              </div>
            ) : results.length === 0 ? (
              <div className="search-empty">
                <p>No results found for "{query}"</p>
              </div>
            ) : (
              <ul role="listbox">
                {results.map((doc, index) => (
                  <li
                    key={doc.id}
                    role="option"
                    aria-selected={index === selectedIndex}
                    className={`search-result${index === selectedIndex ? ' is-selected' : ''}`}
                  >
                    <Link
                      href={doc.path}
                      onClick={() => setOpen(false)}
                      className="search-result-link"
                    >
                      <div className="search-result-title">{doc.title}</div>
                      <div className="search-result-desc">{doc.description}</div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Footer */}
          <div className="search-footer">
            <div className="search-shortcuts">
              <span>
                <kbd>↑↓</kbd> Navigate
              </span>
              <span>
                <kbd>↵</kbd> Select
              </span>
              <span>
                <kbd>Esc</kbd> Close
              </span>
            </div>
          </div>
        </div>
      </dialog>
    </>
  )
}
