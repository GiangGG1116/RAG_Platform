import React, { useState, useEffect, useRef } from 'react';
import type { AppSettings, DocumentInfo } from '../services/api';
import { listDocuments, createDocument, deleteDocument, getDocumentStatus } from '../services/api';

interface DocManagerProps {
  settings: AppSettings;
}

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const READABLE_EXTENSIONS = new Set([
  'txt',
  'md',
  'markdown',
  'csv',
  'json',
  'html',
  'htm',
  'log',
  'xml',
  'yaml',
  'yml',
]);

const DOC_TYPE_BY_EXTENSION: Record<string, string> = {
  txt: 'text',
  md: 'md',
  markdown: 'md',
  html: 'html',
  htm: 'html',
  pdf: 'pdf',
};

const getExtension = (fileName: string) => {
  const parts = fileName.toLowerCase().split('.');
  return parts.length > 1 ? parts.pop() || '' : '';
};

const getTitleFromFileName = (fileName: string) => {
  const lastDot = fileName.lastIndexOf('.');
  return lastDot > 0 ? fileName.slice(0, lastDot) : fileName;
};

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const isReadableTextFile = (file: File) => {
  const extension = getExtension(file.name);
  return (
    file.type.startsWith('text/') ||
    file.type === 'application/json' ||
    file.type === 'application/xml' ||
    file.type === 'application/x-yaml' ||
    READABLE_EXTENSIONS.has(extension)
  );
};

const isPdfFile = (file: File) => {
  return file.type === 'application/pdf' || getExtension(file.name) === 'pdf';
};

const inferDocType = (file: File) => {
  if (isPdfFile(file)) return 'pdf';
  const extension = getExtension(file.name);
  return DOC_TYPE_BY_EXTENSION[extension] || 'text';
};

const extractPdfText = async (file: File) => {
  const { GlobalWorkerOptions, getDocument } = await import('pdfjs-dist');
  GlobalWorkerOptions.workerSrc = '/pdf.worker.min.js';

  const loadingTask = getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
  const pdf = await loadingTask.promise;
  const pageCount = pdf.numPages;
  const pages: string[] = [];

  try {
    for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber);
      const textContent = await page.getTextContent();
      const pageText = textContent.items
        .map((item) => {
          if (!('str' in item)) return '';
          return `${item.str}${item.hasEOL ? '\n' : ' '}`;
        })
        .join('')
        .trim();

      if (pageText) {
        pages.push(pageText);
      }
    }
  } finally {
    await pdf.destroy();
  }

  return {
    content: pages.join('\n\n'),
    pageCount,
  };
};

export const DocManager: React.FC<DocManagerProps> = ({ settings }) => {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ingestion State
  const [ingesting, setIngesting] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number; filename: string } | null>(null);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const pollingIntervals = useRef<Record<string, any>>({});

  const fetchDocs = async (targetPage = page) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments(settings, targetPage, pageSize);
      setDocuments(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  // Poll status for processing documents
  const startPolling = (docId: string) => {
    if (pollingIntervals.current[docId]) return;

    const interval = setInterval(async () => {
      try {
        const statusData = await getDocumentStatus(settings, docId);
        
        setDocuments((prevDocs) =>
          prevDocs.map((doc) => {
            if (doc.id === docId) {
              const updatedDoc = {
                ...doc,
                status: statusData.status,
                chunk_count: statusData.chunk_count,
                error_message: statusData.error_message,
              };

              // Clear interval if processing is complete
              if (statusData.status === 'completed' || statusData.status === 'failed') {
                clearInterval(pollingIntervals.current[docId]);
                delete pollingIntervals.current[docId];
              }
              return updatedDoc;
            }
            return doc;
          })
        );
      } catch (err) {
        console.error(`Failed to poll status for ${docId}:`, err);
      }
    }, 3000);

    pollingIntervals.current[docId] = interval;
  };

  // Load documents on mount and setting change
  useEffect(() => {
    fetchDocs(page);

    return () => {
      // Clean up all intervals on unmount
      Object.values(pollingIntervals.current).forEach(clearInterval);
      pollingIntervals.current = {};
    };
  }, [settings.apiKey, settings.apiUrl, settings.tenantId, page]);

  // Watch documents to start polling for any processing item
  useEffect(() => {
    documents.forEach((doc) => {
      if (doc.status === 'processing' || doc.status === 'pending') {
        startPolling(doc.id);
      }
    });
  }, [documents]);

  const processFilesBatch = async (files: FileList | File[] | undefined | null) => {
    if (!files || files.length === 0) return;
    
    setIngestError(null);
    const fileArray = Array.from(files).filter(f => isPdfFile(f) || isReadableTextFile(f));
    
    if (fileArray.length === 0) {
      setIngestError('No supported files found (PDF, TXT, MD, CSV, HTML, JSON, etc.)');
      return;
    }

    const overSizeFiles = fileArray.filter(f => f.size > MAX_UPLOAD_BYTES);
    if (overSizeFiles.length > 0) {
      setIngestError(`${overSizeFiles.length} files exceed the ${formatFileSize(MAX_UPLOAD_BYTES)} limit.`);
      return;
    }

    setIngesting(true);
    setBatchProgress({ current: 0, total: fileArray.length, filename: '' });

    let successCount = 0;
    const errors: string[] = [];

    for (let i = 0; i < fileArray.length; i++) {
      const file = fileArray[i];
      setBatchProgress({ current: i + 1, total: fileArray.length, filename: file.name });

      try {
        const extractedPdf = isPdfFile(file) ? await extractPdfText(file) : null;
        const fileContent = extractedPdf ? extractedPdf.content : await file.text();
        
        if (!fileContent.trim()) {
           errors.push(`${file.name}: No readable text found.`);
           continue;
        }

        const docTitle = getTitleFromFileName(file.name);
        const inferredDocType = inferDocType(file);
        const fileMetadata = {
            source: 'frontend-file-upload',
            filename: file.name,
            file_size: file.size,
            file_type: file.type || 'unknown',
            ...(extractedPdf?.pageCount ? { page_count: extractedPdf.pageCount } : {}),
        };

        const newDoc = await createDocument(settings, docTitle, fileContent, inferredDocType, fileMetadata);
        successCount++;
        
        setDocuments((prev) => [newDoc, ...prev.slice(0, pageSize - 1)]);
        setTotal((prev) => prev + 1);
        startPolling(newDoc.id);

      } catch (err: any) {
        console.error(`Failed to ingest ${file.name}:`, err);
        errors.push(`${file.name}: ${err.message || 'Unknown error'}`);
      }
    }

    setIngesting(false);
    setBatchProgress(null);
    
    if (successCount === 0) {
        const errorDetail = errors.length > 0 ? errors.slice(0, 3).join(' | ') : "Failed to ingest any files.";
        setIngestError(`Error: ${errorDetail}${errors.length > 3 ? '...' : ''}`);
    } else if (errors.length > 0) {
        // Some succeeded, some failed
        alert(`Partially completed. ${errors.length} files failed:\n` + errors.slice(0, 5).join('\n'));
        fetchDocs(1);
    } else {
        fetchDocs(1);
    }
    
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (folderInputRef.current) folderInputRef.current.value = '';
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    processFilesBatch(e.target.files);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingFile(false);
    processFilesBatch(e.dataTransfer.files);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDraggingFile(true);
  };

  const handleDragLeave = () => {
    setIsDraggingFile(false);
  };

  const handleDelete = async (docId: string) => {
    if (!confirm('Are you sure you want to delete this document? All vector chunks will be removed.')) {
      return;
    }

    try {
      if (pollingIntervals.current[docId]) {
        clearInterval(pollingIntervals.current[docId]);
        delete pollingIntervals.current[docId];
      }

      await deleteDocument(settings, docId);
      
      // Refresh documents list
      fetchDocs();
    } catch (err: any) {
      alert(err.message || 'Failed to delete document');
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="doc-manager-container">
      <div className="panel-header">
        <div>
          <h2>Document Management</h2>
          <div className="panel-title-desc">Upload, process, and manage PDF or text files for the RAG search index.</div>
        </div>
        <button className="btn btn-secondary" onClick={() => fetchDocs(page)} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh List'}
        </button>
      </div>

      {error && (
        <div style={{ padding: '12px 16px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '8px', color: '#fca5a5', fontSize: '14px' }}>
          Error: {error}
        </div>
      )}

      <div className="doc-grid">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="doc-table-container">
            {loading && documents.length === 0 ? (
              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '60px' }}>
                <svg className="spinner" viewBox="0 0 50 50">
                  <circle className="path" cx="25" cy="25" r="20" fill="none" strokeWidth="5"></circle>
                </svg>
              </div>
            ) : documents.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <svg width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"></path>
                  </svg>
                </div>
                <h3>No documents ingested</h3>
                <p style={{ maxWidth: '400px', margin: '8px 0 0 0', fontSize: '13px' }}>
                  Upload a PDF or text document to start generating embedding vector chunks.
                </p>
              </div>
            ) : (
              <table className="doc-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Chunks</th>
                    <th>Created At</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td style={{ fontWeight: '500' }}>
                        <div style={{ maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {doc.title}
                        </div>
                      </td>
                      <td style={{ textTransform: 'uppercase', fontSize: '12px' }}>{doc.doc_type}</td>
                      <td>
                        <span className={`badge badge-${doc.status}`}>
                          {doc.status}
                        </span>
                        {doc.error_message && (
                          <div style={{ fontSize: '10px', color: '#fca5a5', marginTop: '4px', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {doc.error_message}
                          </div>
                        )}
                      </td>
                      <td>{doc.chunk_count}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
                        {new Date(doc.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <button className="btn btn-danger" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => handleDelete(doc.id)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {totalPages > 1 && (
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '8px' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '8px 12px' }}
                onClick={() => setPage((p) => Math.max(p - 1, 1))}
                disabled={page === 1}
              >
                Previous
              </button>
              <span style={{ alignSelf: 'center', fontSize: '14px', color: 'var(--text-secondary)' }}>
                Page {page} of {totalPages}
              </span>
              <button
                className="btn btn-secondary"
                style={{ padding: '8px 12px' }}
                onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                disabled={page === totalPages}
              >
                Next
              </button>
            </div>
          )}
        </div>

        {/* Right Side: Ingestion Form */}
        <div className="ingest-card">
          <h3>Upload Documents</h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
            Select individual files or an entire folder to batch extract, chunk, and embed them automatically.
          </p>

          <div
            className={`file-dropzone ${isDraggingFile ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            style={{ padding: '40px 20px', minHeight: '200px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}
          >
            <div className="file-dropzone-icon" style={{ marginBottom: '16px' }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M20 16.5V19a2 2 0 01-2 2H6a2 2 0 01-2-2v-2.5" />
              </svg>
            </div>
            
            <strong style={{ fontSize: '16px', marginBottom: '8px' }}>Drag and drop files here</strong>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '24px' }}>
              Supported: PDF, TXT, MD, CSV, JSON, HTML, XML, YAML, LOG
            </span>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button 
                className="btn btn-primary" 
                onClick={() => !ingesting && fileInputRef.current?.click()}
                disabled={ingesting}
              >
                Select Files
              </button>
              <button 
                className="btn btn-secondary" 
                onClick={() => !ingesting && folderInputRef.current?.click()}
                disabled={ingesting}
              >
                Select Folder
              </button>
            </div>

            {/* Hidden inputs */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.txt,.md,.markdown,.csv,.json,.html,.htm,.log,.xml,.yaml,.yml,application/pdf,text/*,application/json,application/xml"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <input
              ref={folderInputRef}
              type="file"
              {...{ webkitdirectory: "", directory: "" } as any}
              multiple
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
          </div>

          {batchProgress && (
            <div style={{ marginTop: '20px', padding: '16px', background: 'var(--bg-secondary)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '14px' }}>
                <strong style={{ color: 'var(--primary-color)' }}>Uploading {batchProgress.current} of {batchProgress.total}</strong>
                <span style={{ color: 'var(--text-muted)' }}>{Math.round((batchProgress.current / batchProgress.total) * 100)}%</span>
              </div>
              <div style={{ width: '100%', background: 'var(--bg-card)', height: '6px', borderRadius: '3px', overflow: 'hidden' }}>
                <div 
                  style={{ 
                    height: '100%', 
                    background: 'var(--primary-color)', 
                    width: `${(batchProgress.current / batchProgress.total) * 100}%`,
                    transition: 'width 0.2s ease-out'
                  }}
                />
              </div>
              <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-secondary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                Processing: {batchProgress.filename}
              </div>
            </div>
          )}

          {ingestError && (
            <div style={{ marginTop: '16px', padding: '12px 16px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '8px', color: '#fca5a5', fontSize: '14px' }}>
              Error: {ingestError}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
