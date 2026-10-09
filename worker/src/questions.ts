import questions from "../../src/masuda_verdict/questions.json";

export type Question = { name: string; instructions: string; choices: Record<string, string> };

export const BODY_QUESTION: Question = questions.body;
export const COMMENT_QUESTION: Question = questions.comment;
export const NARRATIVE_QUESTION: Question = questions.narrative;
