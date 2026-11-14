/** "Start from" shortcuts on Home. Each one prefills the new-deck prompt; none needs a file. */
export const STARTERS = [
  {
    key: "notes",
    title: "Notes to deck",
    hint: "Paste rough notes",
    prompt: "Turn my rough notes into a clear deck. Keep my points, fix the order, and write each headline as a claim.\n\nMy notes:\n",
  },
  {
    key: "report",
    title: "Report to summary",
    hint: "Long text, short deck",
    prompt: "Summarise the report below in a short deck for someone who will not read the report. Lead with the conclusion.\n\nThe report:\n",
  },
  {
    key: "pitch",
    title: "Pitch deck",
    hint: "Problem, proof, ask",
    prompt: "A pitch deck: the problem, why now, what we built, proof that it works, the market, the team, and the ask.\n\nThe company: ",
  },
  {
    key: "update",
    title: "Team update",
    hint: "Progress, risks, next steps",
    prompt: "An update for my team: what we shipped, what slipped and why, the risks, and what happens next.\n\nThe details: ",
  },
  {
    key: "numbers",
    title: "From numbers",
    hint: "Paste figures, get charts",
    prompt: "Build a deck around the numbers below. Pick the chart that fits each point and say what each number means.\n\nThe numbers:\n",
  },
] as const;

export type StarterKey = (typeof STARTERS)[number]["key"];

/** Example prompts on the new-deck screen. */
export const EXAMPLES = [
  { title: "Pitch to investors", prompt: "A 10 slide seed pitch for a meal-kit startup raising $1.5M." },
  { title: "Teach a lesson", prompt: "Explain the water cycle to 11 year olds in 8 slides, with a quiz." },
  { title: "Report to a board", prompt: "Our Q3 board review. Revenue is up 34%, but monthly logo churn went from 2.6% to 4.1%. I need the board to approve a retention budget." },
  { title: "Make a recommendation", prompt: "Compare three CRM tools for a 12 person sales team and recommend one, in 6 slides." },
] as const;

export const AUDIENCES = ["General audience", "Board of directors", "Executives", "Investors", "Customers", "My team", "Students"];
export const LENGTHS = [5, 8, 10, 12, 15, 20];
export const TONES = ["Direct, no spin", "Warm and encouraging", "Formal", "Persuasive", "Light and playful"];
