const { Quiz, Question, UserQuizAttempt } = require('../models')
const { generateFeedback, generateAIQuiz } = require('../utils/generateFeedback')
const config = require('../config/config')
const { v4: uuidv4 } = require('uuid')
const fs = require('fs')
const path = require('path')
const { promisify } = require('util')
const { exec } = require('child_process')
const execAsync = promisify(exec)
const os = require('os')

module.exports = {
  // Create a quiz manually from provided payload
  async createQuiz(req, res) {
    try {
      const { title, subject, description, isPublic = true, questions } = req.body

      if (!title || !subject || !Array.isArray(questions) || questions.length === 0) {
        return res.status(400).send({ error: 'Title, subject and at least one question are required' })
      }

      // Validate questions array
      const questionIds = []
      for (const [idx, q] of questions.entries()) {
        if (!q.question || !Array.isArray(q.options) || q.options.length !== 4 || !q.correctAnswer) {
          return res.status(400).send({ error: `Invalid question format at index ${idx}` })
        }
        if (!q.options.includes(q.correctAnswer)) {
          return res.status(400).send({ error: `Correct answer must be one of the options for question ${idx + 1}` })
        }

        const questionDoc = new Question({
          question: q.question,
          options: q.options,
          correctAnswer: q.correctAnswer,
          explanation: q.explanation || ''
        })
        await questionDoc.save()
        questionIds.push(questionDoc._id)
      }

      // Create quiz document
      const quizDoc = new Quiz({
        title,
        subject,
        description: description || '',
        isPublic,
        createdBy: req.verifiedAccessToken.id,
        questions: questionIds
      })
      await quizDoc.save()

      res.status(201).send({ quizId: quizDoc._id })
    } catch (error) {
      console.error('Error creating quiz:', error)
      res.status(500).send({ error: 'Failed to create quiz' })
    }
  },

  // Get quizzes
  async getQuizzesForUser(req, res) {
    try {
      const userId = req.params.userId || req.verifiedAccessToken?.id
      const filter = { createdBy: userId }

      const quizzes = await Quiz.find(filter)
        .select('_id title subject description questions createdAt')
        .populate('questions')

      // Add question count to each quiz object
      const quizzesWithCount = quizzes.map(quiz => ({
        ...quiz.toObject(),
        questionsCount: quiz.questions.length
      }))

      res.send(quizzesWithCount)
    } catch (err) {
      console.error(err)
      res.status(500).send({ error: 'Failed to fetch quizzes' })
    }
  },

  async getQuiz(req, res) {
    try {
      const quiz = await Quiz.findById(req.params.quizId).populate('questions')
      if (!quiz) return res.status(404).send({ error: 'Quiz not found' })
      res.send({ quiz })
    } catch (err) {
      console.error(err)
      res.status(500).send({ error: 'Failed to fetch quiz' })
    }
  },

  async getAttemptResults(req, res) {
    try {
      const { attemptId } = req.params
      const userId = req.params.userId || req.verifiedAccessToken?.id

      // Find the specific attempt
      const attempt = await UserQuizAttempt.findById(attemptId)
        .populate({
          path: 'quizId',
          populate: { path: 'questions' }
        })

      if (!attempt) {
        return res.status(404).send({ error: 'Quiz attempt not found' })
      }

      // Verify ownership
      if (attempt.userId !== userId) {
        return res.status(403).send({ error: 'Not authorized to view this attempt' })
      }

      // Verify completion
      if (!attempt.completed) {
        return res.status(400).send({ error: 'Quiz attempt not completed yet' })
      }

      // Extract user answers as indices
      const userAnswers = attempt.answers.map(answer => {
        const question = attempt.quizId.questions.find(q => q._id.toString() === answer.questionId.toString())
        if (question) {
          return question.options.indexOf(answer.userAnswer)
        }
        return -1
      })

      const results = {
        score: attempt.score,
        totalQuestions: attempt.quizId.questions.length,
        correct: attempt.answers.filter(a => a.isCorrect).length,
        strengths: attempt.feedback_strengths || '',
        improvements: attempt.feedback_areasForImprovement || ''
      }

      res.send({ 
        results, 
        userAnswers,
        quiz: attempt.quizId
      })
    } catch (err) {
      console.error('Error fetching attempt results:', err)
      res.status(500).send({ error: 'Failed to fetch attempt results' })
    }
  },

  async getUserQuizAttempts(req, res) {
    try {

      const userId = req.params.userId || req.verifiedAccessToken?.id

      // Find all completed attempts for the user
      const attempts = await UserQuizAttempt.find({ 
        userId, 
        completed: true 
      })
      .populate({
        path: 'quizId',
        select: 'title subject description'
      })
      .sort({ endTime: -1 }) // Most recent first

      // Filter out attempts where the quiz no longer exists (orphaned references)
      const validAttempts = attempts.filter(attempt => attempt.quizId != null)

      // Format the response
      const formattedAttempts = validAttempts.map(attempt => ({
        _id: attempt._id,
        score: attempt.score,
        totalQuestions: attempt.answers.length,
        correctAnswers: attempt.answers.filter(a => a.isCorrect).length,
        endTime: attempt.endTime,
        quiz: {
          _id: attempt.quizId._id,
          title: attempt.quizId.title,
          subject: attempt.quizId.subject,
          description: attempt.quizId.description
        }
      }))

      res.send({ attempts: formattedAttempts })
    } catch (err) {
      console.error('Error fetching user quiz attempts:', err)
      res.status(500).send({ error: 'Failed to fetch user quiz attempts' })
    }
  },
  // Start attempt
  async startQuizAttempt(req, res) {
    try {
      const { quizId } = req.params
      const quiz = await Quiz.findById(quizId)
      if (!quiz) return res.status(404).send({ error: 'Quiz not found' })

      // Get userId from either JWT token (internal) or URL parameter (external API)
      const userId = req.params.userId || req.verifiedAccessToken?.id

      if (!userId) {
        return res.status(400).send({ error: 'User ID is required' })
      }

      const attempt = new UserQuizAttempt({
        userId: userId,
        quizId,
        answers: []
      })
      await attempt.save()
      res.status(201).send({ attemptId: attempt._id })
    } catch (err) {
      console.error(err)
      res.status(500).send({ error: 'Failed to start attempt' })
    }
  },

  // Complete attempt
  async completeQuizAttempt(req, res) {
    try {
      const { attemptId } = req.params
      const { answers: submittedAnswerIndices } = req.body // Array of selected option indices

      console.log('answers:', submittedAnswerIndices)

      if (!Array.isArray(submittedAnswerIndices)) {
        return res.status(400).send({ error: 'Invalid format: answers must be an array.' })
      }      // Populate quiz and its questions
      const attempt = await UserQuizAttempt.findById(attemptId)
        .populate({
          path: 'quizId',
          populate: { path: 'questions' }
        })

      if (!attempt) return res.status(404).send({ error: 'Attempt not found' })
      
      // Get userId from either JWT token (internal) or URL parameter (external API)
      const userId = req.params.userId || req.verifiedAccessToken?.id
      
      if (attempt.userId !== userId) return res.status(403).send({ error: 'Not your attempt' })
      if (attempt.completed) return res.status(400).send({ error: 'Attempt already completed.' })

      const questions = attempt.quizId.questions
      const totalQuestions = questions.length

      if (submittedAnswerIndices.length !== totalQuestions) {
        return res.status(400).send({ error: `Incorrect number of answers submitted. Expected ${totalQuestions}.` })
      }

      // Process answers
      const processedAnswers = []
      let correctCount = 0

      for (let i = 0; i < totalQuestions; i++) {
        const question = questions[i]
        const submittedIndex = submittedAnswerIndices[i]

        // Basic validation
        if (submittedIndex === null || submittedIndex === undefined || submittedIndex < 0 || submittedIndex >= question.options.length) {
          return res.status(400).send({ error: `Invalid answer index for question ${i + 1}.` })
        }

        const userAnswer = question.options[submittedIndex]
        const isCorrect = userAnswer === question.correctAnswer

        if (isCorrect) {
          correctCount++
        }

        processedAnswers.push({
          questionId: question._id,
          userAnswer,
          isCorrect
        })
      }

      // Update attempt document
      attempt.answers = processedAnswers
      attempt.score = (correctCount / totalQuestions) * 100
      attempt.completed = true
      attempt.endTime = new Date()

      // Generate feedback using Gemini (falls back if API key missing)
      let feedback = { strengths: '', improvements: '' }
      try {
        feedback = await generateFeedback(questions, processedAnswers)
        // Save feedback in attempt document
        attempt.feedback_strengths = feedback.strengths
        attempt.feedback_areasForImprovement = feedback.improvements
        await attempt.save()
      } catch (fbErr) {
        console.error('Feedback generation failed:', fbErr)
      }

      res.send({ attemptId: attempt._id })
    } catch (err) {
      console.error(err)
      res.status(500).send({ error: 'Failed to complete attempt' })
    }
  },
  
  async createAIQuiz(req, res) {
    try {
      const { course, user_id } = req.body

      if (!course || !course.name) {
        return res.status(400).send({ error: 'Course information is required' })
      }

      const course_name = course.name
      const course_description = course.description
      
      // Get detailed course information
      const course_details = getDetailedCourseInfo(course_name)
      
      // Create comprehensive content from catalog data
      const document_content = createDocumentContent(course_name, course_details, course_description)
      
      const id = uuidv4()

      // Step 1: Create collection and upload content
      await chiselCreateCollection(id)
      await chiselUploadDocument(id, document_content)
      
      // Step 2: Lookup relevant content
      const data = await chiselLookup(course_name, id)

      // Step 3: Generate quiz using AI
      console.log('Generating quiz questions using AI...')
      const generatedQuiz = await generateAIQuiz(data, course_name)

      // Step 4: Save questions to database
      const questionIds = []
      for (const q of generatedQuiz.questions) {
        const questionDoc = new Question({
          question: q.question,
          options: q.options,
          correctAnswer: q.correctAnswer,
          explanation: q.explanation || ''
        })
        await questionDoc.save()
        questionIds.push(questionDoc._id)
      }

      // Determine the creator ID
      let createdBy
      if (user_id) {
        createdBy = user_id
      } else {
        createdBy = req.verifiedAccessToken?.id || 'a6123882-efc3-4a3d-a5ee-6dcf78be1629'
      }

      // Step 5: Create quiz document
      const quizDoc = new Quiz({
        title: generatedQuiz.title,
        subject: course_name,
        description: generatedQuiz.description,
        isPublic: true,
        createdBy: createdBy,
        questions: questionIds
      })
      quizDoc.courseId = req.body.course.id;
      await quizDoc.save()
      
      // Step 6: Clean up collection
      await chiselDeleteCollection(id)

      console.log(`AI Quiz created successfully with ${generatedQuiz.questions.length} questions`)
      res.status(201).send({ 
        quizId: quizDoc._id,
        title: generatedQuiz.title,
        description: generatedQuiz.description,
        questionsCount: generatedQuiz.questions.length
      })
    } catch (err) {
      console.error('Error creating AI quiz:', err)
      res.status(500).send({ error: 'Failed to create AI quiz: ' + err.message })
    }
  },

  async getCourseCategories(req, res) {
    try {
      const catalogPath = path.join(__dirname, '../data/course_catalog.json')
      const catalogData = JSON.parse(fs.readFileSync(catalogPath, 'utf8'))
      res.send(catalogData)
    } catch (err) {
      console.error('Error reading course catalog:', err)
      res.status(500).send({ error: 'Failed to fetch course catalog' })
    }
  }
}

async function chiselLookup(name, description) {      
  const chiselLookupUrl = config.chiselUrl.url + '/lookup'
  const response = await fetch(chiselLookupUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ 
      query: name,
      collection: description
    })
  })
  
  if (!response.ok) {
    throw new Error(`Chisel API error: ${response.status} ${response.statusText}`)
  }
  
  const data = await response.json()
  return data
}

async function chiselCreateCollection(id) {
  const createCollectionUrl = config.chiselUrl.url + '/create-collection'
  const response = await fetch(createCollectionUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ 
      name: id
    })
  })
  
  if (!response.ok) {
    const errorBody = await response.text()
    throw new Error(`Chisel API error: ${response.status} ${response.statusText} - ${errorBody}`)
  }
  
  const data = await response.json()
  console.log('CreateCollection OK:', data)
  return data
}

async function chiselUploadDocument(id, description) {
  const chunkUrl = config.chiselUrl.url + '/chunk'
  const response = await fetch(chunkUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ 
      text: description,
      origin: "AiTutorQuiz",
      collection: id
    })
  })
  
  if (response.status !== 200) {
    const errorBody = await response.text()
    throw new Error(`Chisel API error (${response.status}): ${errorBody}`)
  }
  
  console.log('Document upload successful')
  return true
}

async function chiselDeleteCollection(id) {
  const deleteCollectionUrl = config.chiselUrl.url + '/delete-collection'
  const response = await fetch(deleteCollectionUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ 
      name: id
    })
  })
  
  if (response.status >= 400) {
    const errorBody = await response.text()
    throw new Error(`Error from server: ${errorBody}`)
  }
  
  const data = await response.text()
  console.log('DeleteCollection OK:', data)
  return data
}

function getDetailedCourseInfo(course_name) {
  try {
    const catalogPath = path.join(__dirname, '../data/course_catalog.json')
    const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'))
    
    // Search for the course in the catalog
    for (const category of catalog.categories || []) {
      for (const course of category.courses || []) {
        if (course.name.toLowerCase() === course_name.toLowerCase()) {
          return course
        }
      }
    }
    
    // If not found, return minimal info
    return { name: course_name, description: "Course information not available" }
    
  } catch (error) {
    console.error('Error loading course catalog:', error)
    return { name: course_name, description: "Course information not available" }
  }
}

function formatCourseDetails(course_details) {
  if (!course_details) {
    return "Course details not available."
  }
  
  let formatted = `Course: ${course_details.name || 'Unknown'}\n\n`
  formatted += `Description: ${course_details.description || 'No description available'}\n\n`
  
  if (course_details.duration) {
    formatted += `Duration: ${course_details.duration}\n`
  }
  
  if (course_details.level) {
    formatted += `Level: ${course_details.level}\n\n`
  }
  
  if (course_details.skills && course_details.skills.length > 0) {
    formatted += "Skills You'll Learn:\n"
    for (const skill of course_details.skills) {
      formatted += `- ${skill}\n`
    }
    formatted += "\n"
  }
  
  if (course_details.projects && course_details.projects.length > 0) {
    formatted += "Projects You'll Build:\n"
    for (const project of course_details.projects) {
      formatted += `- ${project}\n`
    }
    formatted += "\n"
  }
  
  if (course_details.career_paths && course_details.career_paths.length > 0) {
    formatted += "Career Opportunities:\n"
    for (const career of course_details.career_paths) {
      formatted += `- ${career}\n`
    }
    formatted += "\n"
  }
  
  return formatted
}

function createDocumentContent(course_name, course_details, course_description) {
  return `COURSE: ${course_name}

DESCRIPTION: ${course_description}

DETAILED COURSE INFORMATION:
${formatCourseDetails(course_details)}

EDUCATIONAL CONTEXT:
This course is designed to provide comprehensive knowledge and practical skills.
Students will gain hands-on experience through real-world projects and exercises.
The curriculum follows industry best practices and includes the latest technologies and methodologies.
`
}