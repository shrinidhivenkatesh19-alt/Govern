import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Upload, X, FileText, Image as ImageIcon, FileType, Loader2 } from "lucide-react";

const ACCEPT = ".pdf,.ppt,.pptx,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.md";
const MAX_MB = 8; // must match backend storage.MAX_UPLOAD_BYTES

function iconFor(filename) {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return ImageIcon;
    if (["pdf"].includes(ext)) return FileType;
    return FileText;
}

function fmtSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function FileUploader({ value, onChange }) {
    const inputRef = useRef(null);
    const [uploading, setUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);

    const uploadOne = async (file) => {
        if (file.size > MAX_MB * 1024 * 1024) {
            toast.error(`${file.name} exceeds ${MAX_MB}MB`);
            return null;
        }
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            return r.data;
        } catch (err) {
            toast.error(err?.response?.data?.detail || `Upload of ${file.name} failed`);
            return null;
        }
    };

    const handleFiles = async (fileList) => {
        const files = Array.from(fileList);
        if (!files.length) return;
        setUploading(true);
        const results = [];
        for (const f of files) {
            const r = await uploadOne(f);
            if (r) results.push(r);
        }
        if (results.length) {
            onChange([...(value || []), ...results]);
            toast.success(`${results.length} file${results.length > 1 ? "s" : ""} uploaded`);
        }
        setUploading(false);
    };

    const remove = (id) => onChange(value.filter((a) => a.id !== id));

    return (
        <div data-testid="file-uploader">
            <span className="label-overline block mb-2">Attachments (PDF, PPT, DOCX, PNG, JPG, etc.)</span>

            <div
                onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                    e.preventDefault();
                    setDragOver(false);
                    handleFiles(e.dataTransfer.files);
                }}
                onClick={() => inputRef.current?.click()}
                data-testid="upload-dropzone"
                className={`border-2 border-dashed p-6 text-center cursor-pointer transition-colors ${
                    dragOver ? "border-[#002FA7] bg-[#F3F4F6]" : "border-border hover:bg-[#F3F4F6]"
                }`}
            >
                <input
                    type="file"
                    ref={inputRef}
                    accept={ACCEPT}
                    multiple
                    onChange={(e) => handleFiles(e.target.files)}
                    className="hidden"
                    data-testid="file-input"
                />
                {uploading ? (
                    <div className="flex items-center justify-center gap-2 text-sm">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Uploading...
                    </div>
                ) : (
                    <>
                        <Upload className="w-6 h-6 mx-auto mb-2 text-muted-foreground" strokeWidth={1.5} />
                        <p className="text-sm font-medium">Click to upload or drag files here</p>
                        <p className="text-xs text-muted-foreground mt-1">PDF, PPT, DOCX, PNG, JPG · Max {MAX_MB}MB each</p>
                    </>
                )}
            </div>

            {value?.length > 0 && (
                <ul className="mt-3 space-y-2" data-testid="uploaded-files-list">
                    {value.map((a) => {
                        const Icon = iconFor(a.original_filename);
                        return (
                            <li
                                key={a.id}
                                className="flex items-center gap-3 px-3 py-2 border border-border bg-white"
                                data-testid={`file-item-${a.id}`}
                            >
                                <Icon className="w-4 h-4 text-[#002FA7] shrink-0" strokeWidth={1.75} />
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium truncate">{a.original_filename}</div>
                                    <div className="text-xs text-muted-foreground font-mono">{fmtSize(a.size)}</div>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => remove(a.id)}
                                    data-testid={`remove-file-${a.id}`}
                                    className="p-1 hover:bg-[#FF2400] hover:text-white transition-colors"
                                >
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}
