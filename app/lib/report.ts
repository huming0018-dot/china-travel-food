export interface ReportResult { accepted: boolean; report_count: number }
export async function submitReport(
  rpc: (name: string, args: { review_id: string }) => PromiseLike<{ data: unknown; error: unknown }>,
  reviewId: string,
): Promise<ReportResult> {
  const { data, error } = await rpc('increment_report', { review_id: reviewId });
  if (error) throw error;
  const result = data as ReportResult | null;
  if (!result || typeof result.accepted !== 'boolean' ||
      !Number.isSafeInteger(result.report_count) || result.report_count < 0) {
    throw new Error('Invalid report response');
  }
  return result;
}

