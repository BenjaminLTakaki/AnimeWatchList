const { GoogleGenAI, Type } = require('@google/genai')
const config = require('../config/config')

async function generateFeedback(questions, processedAnswers) {
  const apiKey = config.gemini.apiKey
  if (!apiKey) {
    // Fallback: simple summarisation without AI
    const incorrect = processedAnswers.filter(a => !a.isCorrect).length
    const correct = processedAnswers.length - incorrect
    return {
      strengths: `You answered ${correct} questions correctly. Good job on those!`,
      improvements: `You missed ${incorrect} questions. Review the related materials to improve.`
    }
  }

  const ai = new GoogleGenAI({ apiKey })

  // Build prompt
  const promptParts = [
    'You are an AI tutor, and I trust you to analyze my quiz attempt with care. Please provide a short JSON with two keys: "strengths" and "improvements". Keep each value concise (max 2 sentences).\n',
    'Here are the questions and my answers:\n'
  ]

  questions.forEach((q, idx) => {
    const pa = processedAnswers[idx]
    const correct = pa.isCorrect ? 'correct' : 'incorrect'
    promptParts.push(`Q${idx + 1}: ${q.question}\nUser answer: ${pa.userAnswer}\nThis answer is ${correct}.\n`)
  })

  const prompt = promptParts.join('')

  console.log('Prompt:', prompt)
  
  const response = await ai.models.generateContent({
    model: 'gemini-2.0-flash',
    contents: prompt,
    config: {
      responseMimeType: 'application/json',
      responseSchema: {
        type: Type.OBJECT,
        properties: {
          strengths: { type: Type.STRING },
          improvements: { type: Type.STRING }
        },
        propertyOrdering: ['strengths', 'improvements']
      }
    }
  })

  let feedback
  try {
    feedback = JSON.parse(response.text)
  } catch {
    // Fallback if not valid JSON
    feedback = {
      strengths: 'Great effort!',
      improvements: 'Review the incorrect questions.'
    }
  }

  return feedback
}

async function generateAIQuiz(data, courseName) {
  const apiKey = config.gemini.apiKey
  if (!apiKey) {
    throw new Error('Gemini API key is required for AI quiz generation')
  }

  const ai = new GoogleGenAI({ apiKey })

  // Extract content from the Chisel API results
  const contentParts = data.result.map(item => {
    if (item.payload && typeof item.payload === 'object') {
      return JSON.stringify(item.payload)
    }
    return String(item.payload || '')
  }).join('\n\n')

  // Build comprehensive prompt
  const prompt = `You are an expert AI tutor creating a comprehensive quiz for the course: "${courseName}".

Based on the following course content and materials:

${contentParts}

Generate a quiz with the following requirements:
1. Create between 10-30 questions (you decide the optimal number based on content depth)
2. Each question should have exactly 4 multiple choice options
3. Include a brief explanation for each correct answer
4. Also provide a comprehensive description for the overall quiz
5. Questions should cover key concepts, practical applications, and test understanding at different levels

Please provide your response as a JSON object with this exact structure:
{
  "title": "Quiz title for ${courseName}",
  "description": "A comprehensive description of what this quiz covers and its learning objectives",
  "questions": [
    {
      "question": "Question text here?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correctAnswer": "The exact text of the correct option",
      "explanation": "Brief explanation of why this answer is correct"
    }
  ]
}

Important: Ensure the correctAnswer field contains the EXACT text that appears in the options array.`

  console.log('Generating AI Quiz with prompt length:', prompt.length)
  
  try {
    const response = await ai.models.generateContent({
      model: 'gemini-2.0-flash',
      contents: prompt,
      config: {
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            title: { type: Type.STRING },
            description: { type: Type.STRING },
            questions: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  question: { type: Type.STRING },
                  options: {
                    type: Type.ARRAY,
                    items: { type: Type.STRING }
                  },
                  correctAnswer: { type: Type.STRING },
                  explanation: { type: Type.STRING }
                },
                propertyOrdering: ['question', 'options', 'correctAnswer', 'explanation']
              }
            }
          },
          propertyOrdering: ['title', 'description', 'questions']
        }
      }
    })

    const quizData = JSON.parse(response.text)
    
    // Validate the response
    if (!quizData.questions || !Array.isArray(quizData.questions) || quizData.questions.length < 10) {
      throw new Error('Generated quiz does not meet minimum requirements')
    }

    // Validate each question
    for (const [idx, q] of quizData.questions.entries()) {
      if (!q.question || !Array.isArray(q.options) || q.options.length !== 4 || !q.correctAnswer) {
        throw new Error(`Invalid question format at index ${idx}`)
      }
      if (!q.options.includes(q.correctAnswer)) {
        throw new Error(`Correct answer not found in options for question ${idx + 1}`)
      }
    }

    console.log(`Generated quiz with ${quizData.questions.length} questions`)
    return quizData
    
  } catch (error) {
    console.error('Error generating AI quiz:', error)
    throw new Error('Failed to generate AI quiz: ' + error.message)
  }
}

module.exports = { generateFeedback, generateAIQuiz }